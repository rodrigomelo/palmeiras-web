package com.palmeiras.agenda

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.RemoteViews
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

class MatchWidgetProvider : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, appWidgetIds: IntArray) {
        val pending = goAsync()
        Thread {
            try {
                val match = runCatching { MatchDataClient.fetchMatches("SCHEDULED,TIMED,IN_PLAY,PAUSED", 1, "men").firstOrNull() }.getOrNull()
                appWidgetIds.forEach { updateWidget(context, manager, it, match) }
            } finally {
                pending.finish()
            }
        }.start()
    }

    private fun updateWidget(context: Context, manager: AppWidgetManager, widgetID: Int, match: AgendaMatch?) {
        val views = RemoteViews(context.packageName, R.layout.match_widget)
        if (match == null) {
            views.setTextViewText(R.id.widget_competition, "PRÓXIMO JOGO")
            views.setTextViewText(R.id.widget_match, "Abra o app para atualizar")
            views.setTextViewText(R.id.widget_kickoff, "Palmeiras Agenda")
            views.setViewVisibility(R.id.widget_live, View.GONE)
        } else {
            val score = if (match.homeScore != null && match.awayScore != null) "  ${match.homeScore}–${match.awayScore}" else ""
            views.setTextViewText(R.id.widget_competition, if (match.status in setOf("IN_PLAY", "PAUSED")) "JOGO EM ANDAMENTO" else "PRÓXIMO JOGO")
            views.setTextViewText(R.id.widget_match, "${match.homeTeam} × ${match.awayTeam}$score")
            views.setTextViewText(R.id.widget_kickoff, formatKickoff(match.utcDate))
            views.setViewVisibility(R.id.widget_live, if (match.status in setOf("IN_PLAY", "PAUSED")) View.VISIBLE else View.GONE)
        }

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            match?.id?.let { putExtra(NotificationSync.EXTRA_MATCH_ID, it) }
        }
        views.setOnClickPendingIntent(
            R.id.widget_root,
            PendingIntent.getActivity(context, widgetID, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        )
        manager.updateAppWidget(widgetID, views)
    }

    private fun formatKickoff(value: String): String {
        return runCatching {
            val date = Instant.parse(value).atZone(ZoneId.of("America/Sao_Paulo"))
            DateTimeFormatter.ofPattern("EEE, dd/MM · HH:mm").format(date)
        }.getOrDefault("Horário a confirmar")
    }
}
