package com.palmeiras.agenda

import android.Manifest
import android.app.AlarmManager
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant

internal data class AgendaMatch(
    val id: String,
    val utcDate: String,
    val status: String,
    val homeTeam: String,
    val awayTeam: String,
    val homeScore: Int?,
    val awayScore: Int?,
    val eventsCount: Int
) {
    val title: String get() = "$homeTeam × $awayTeam"
}

internal object MatchDataClient {
    fun fetchMatches(status: String, limit: Int, scope: String): List<AgendaMatch> {
        val url = URL("${ApiConfig.API_BASE_URL}/matches?status=$status&limit=$limit&team_scope=$scope")
        val root = requestJson(url)
        val matches = root.getJSONArray("matches")
        return buildList {
            for (index in 0 until matches.length()) {
                val item = matches.getJSONObject(index)
                val home = item.getJSONObject("homeTeam")
                val away = item.getJSONObject("awayTeam")
                add(
                    AgendaMatch(
                        id = item.opt("id")?.toString() ?: continue,
                        utcDate = item.optString("utcDate"),
                        status = item.optString("status"),
                        homeTeam = home.optString("shortName", home.optString("name", "Palmeiras")),
                        awayTeam = away.optString("shortName", away.optString("name", "Adversário")),
                        homeScore = item.optIntOrNull("homeScore"),
                        awayScore = item.optIntOrNull("awayScore"),
                        eventsCount = item.optJSONArray("events")?.length() ?: 0
                    )
                )
            }
        }
    }

    fun fetchLatestNews(): Pair<String, String>? {
        val root = requestJson(URL("${ApiConfig.API_BASE_URL}/news?limit=1"))
        val item = root.optJSONArray("news")?.optJSONObject(0) ?: return null
        val title = item.optString("title")
        if (title.isBlank()) return null
        return (item.opt("id")?.toString() ?: item.optString("url", title)) to title
    }

    private fun requestJson(url: URL): JSONObject {
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 12_000
            readTimeout = 12_000
            requestMethod = "GET"
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "PalmeirasAgendaAndroid/${ApiConfig.APP_VERSION}")
        }
        return try {
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}")
            JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }

    private fun JSONObject.optIntOrNull(key: String): Int? =
        if (isNull(key) || !has(key)) null else optInt(key)
}

internal object NotificationSync {
    const val CHANNEL_MATCHES = "match_alerts"
    const val CHANNEL_NEWS = "news"
    const val EXTRA_MATCH_ID = "match_id"
    private const val JOB_ID = 26072026

    fun initialize(context: Context) {
        createChannels(context)
        schedulePeriodic(context)
        synchronizeAsync(context)
    }

    fun synchronizeAsync(context: Context) {
        val appContext = context.applicationContext
        Thread {
            runCatching { synchronize(appContext) }
        }.start()
    }

    fun synchronize(context: Context) {
        val preferences = context.getSharedPreferences(NativeSettingsView.PREFERENCES, Context.MODE_PRIVATE)
        val scope = preferences.getString(NativeSettingsView.KEY_TEAM_SCOPE, NativeSettingsView.TEAM_MEN)
            ?: NativeSettingsView.TEAM_MEN
        val upcoming = MatchDataClient.fetchMatches("SCHEDULED,TIMED,IN_PLAY,PAUSED", 40, scope)
        scheduleMatchAlarms(context, upcoming)
        reconcileMatchChanges(context, upcoming)
        reconcileResult(context, scope)
        reconcileNews(context)
        preferences.edit().putLong("last_successful_sync", System.currentTimeMillis()).apply()
    }

    private fun schedulePeriodic(context: Context) {
        val scheduler = context.getSystemService(JobScheduler::class.java)
        val request = JobInfo.Builder(JOB_ID, ComponentName(context, NotificationJobService::class.java))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPeriodic(15 * 60 * 1000L)
            .setPersisted(true)
            .build()
        scheduler.schedule(request)
    }

    private fun createChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_MATCHES, "Alertas de jogos", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Horários, início, placares e lances do Palmeiras"
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_NEWS, "Notícias", NotificationManager.IMPORTANCE_DEFAULT)
        )
    }

    private fun scheduleMatchAlarms(context: Context, matches: List<AgendaMatch>) {
        val preferences = context.getSharedPreferences(NativeSettingsView.PREFERENCES, Context.MODE_PRIVATE)
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        preferences.getStringSet("scheduled_alarm_ids", emptySet()).orEmpty().forEach { token ->
            val code = token.toIntOrNull() ?: return@forEach
            alarmManager.cancel(alarmPendingIntent(context, code, null, null, null))
        }
        val scheduledCodes = mutableSetOf<String>()
        for (match in matches.filter { it.status == "SCHEDULED" || it.status == "TIMED" }) {
            val kickoff = runCatching { Instant.parse(match.utcDate).toEpochMilli() }.getOrNull() ?: continue
            if (preferences.getBoolean(NativeSettingsView.KEY_ONE_HOUR, false)) {
                val code = "${match.id}.one-hour".hashCode()
                setAlarm(context, alarmManager, code, kickoff - 3_600_000, "Palmeiras Agenda", "${match.title} começa em 1 hora.", match.id)
                scheduledCodes += code.toString()
            }
            if (preferences.getBoolean(NativeSettingsView.KEY_KICKOFF, false)) {
                val code = "${match.id}.kickoff".hashCode()
                setAlarm(context, alarmManager, code, kickoff, "Bola rolando", match.title, match.id)
                scheduledCodes += code.toString()
            }
        }
        preferences.edit().putStringSet("scheduled_alarm_ids", scheduledCodes).apply()
    }

    private fun setAlarm(
        context: Context,
        manager: AlarmManager,
        requestCode: Int,
        time: Long,
        title: String,
        body: String,
        matchID: String
    ) {
        if (time <= System.currentTimeMillis()) return
        manager.setAndAllowWhileIdle(
            AlarmManager.RTC_WAKEUP,
            time,
            alarmPendingIntent(context, requestCode, title, body, matchID)
        )
    }

    private fun alarmPendingIntent(
        context: Context,
        requestCode: Int,
        title: String?,
        body: String?,
        matchID: String?
    ): PendingIntent {
        val intent = Intent(context, MatchAlertReceiver::class.java).apply {
            action = "com.palmeiras.agenda.MATCH_ALERT.$requestCode"
            putExtra("title", title)
            putExtra("body", body)
            putExtra(EXTRA_MATCH_ID, matchID)
        }
        return PendingIntent.getBroadcast(context, requestCode, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun reconcileMatchChanges(context: Context, matches: List<AgendaMatch>) {
        val preferences = context.getSharedPreferences(NativeSettingsView.PREFERENCES, Context.MODE_PRIVATE)
        val previous = preferences.getStringSet("match_snapshots", emptySet()).orEmpty()
            .associate { it.substringBefore('=') to it.substringAfter('=') }
        val current = matches.associate { match ->
            match.id to "${match.utcDate}|${match.status}|${match.homeScore ?: -1}|${match.awayScore ?: -1}|${match.eventsCount}"
        }
        matches.forEach { match ->
            val old = previous[match.id] ?: return@forEach
            val now = current.getValue(match.id)
            if (old == now) return@forEach
            if (preferences.getBoolean(NativeSettingsView.KEY_SCHEDULE_CHANGES, false) && old.substringBefore('|') != match.utcDate) {
                showNotification(context, CHANNEL_MATCHES, "Horário atualizado", "Confira a nova programação de ${match.title}.", match.id)
            }
            val oldEvents = old.substringAfterLast('|').toIntOrNull() ?: 0
            if (preferences.getBoolean(NativeSettingsView.KEY_LIVE_EVENTS, false) && match.status in setOf("IN_PLAY", "PAUSED") && match.eventsCount > oldEvents) {
                showNotification(context, CHANNEL_MATCHES, "Lance no jogo", "Há uma atualização em ${match.title}.", match.id)
            }
        }
        preferences.edit().putStringSet("match_snapshots", current.map { "${it.key}=${it.value}" }.toSet()).apply()
    }

    private fun reconcileResult(context: Context, scope: String) {
        val preferences = context.getSharedPreferences(NativeSettingsView.PREFERENCES, Context.MODE_PRIVATE)
        val match = MatchDataClient.fetchMatches("FINISHED,PLAYING_TIME_FINISHED", 1, scope).firstOrNull() ?: return
        val key = "last_result_id.$scope"
        val previous = preferences.getString(key, null)
        preferences.edit().putString(key, match.id).apply()
        if (previous == null || previous == match.id || !preferences.getBoolean(NativeSettingsView.KEY_RESULTS, false)) return
        val spoilerFree = preferences.getBoolean(NativeSettingsView.KEY_SPOILER_FREE, false)
        val body = if (spoilerFree) "O jogo terminou. Toque para ver o resultado." else "${match.title}: ${match.homeScore ?: 0}–${match.awayScore ?: 0}."
        showNotification(context, CHANNEL_MATCHES, "Fim de jogo", body, match.id)
    }

    private fun reconcileNews(context: Context) {
        val preferences = context.getSharedPreferences(NativeSettingsView.PREFERENCES, Context.MODE_PRIVATE)
        val item = MatchDataClient.fetchLatestNews() ?: return
        val previous = preferences.getString("last_news_id", null)
        preferences.edit().putString("last_news_id", item.first).apply()
        if (previous == null || previous == item.first || !preferences.getBoolean(NativeSettingsView.KEY_NEWS, false)) return
        showNotification(context, CHANNEL_NEWS, "Notícia do Palmeiras", item.second, null)
    }

    fun showNotification(context: Context, channel: String, title: String, body: String, matchID: String?) {
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val launch = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(EXTRA_MATCH_ID, matchID)
        }
        val pending = PendingIntent.getActivity(
            context,
            (matchID ?: title).hashCode(),
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = android.app.Notification.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_launcher_monochrome)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(android.app.Notification.BigTextStyle().bigText(body))
            .setContentIntent(pending)
            .setAutoCancel(true)
            .setColor(NativePalette.brand)
            .build()
        context.getSystemService(NotificationManager::class.java).notify((matchID ?: "$title$body").hashCode(), notification)
    }
}

class MatchAlertReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        NotificationSync.showNotification(
            context,
            NotificationSync.CHANNEL_MATCHES,
            intent.getStringExtra("title") ?: "Palmeiras Agenda",
            intent.getStringExtra("body") ?: "Confira a agenda.",
            intent.getStringExtra(NotificationSync.EXTRA_MATCH_ID)
        )
    }
}

class NotificationJobService : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        Thread {
            val success = runCatching { NotificationSync.synchronize(applicationContext) }.isSuccess
            jobFinished(params, !success)
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters): Boolean = true
}
