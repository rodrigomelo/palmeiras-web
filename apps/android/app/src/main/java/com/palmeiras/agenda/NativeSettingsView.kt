package com.palmeiras.agenda

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import kotlin.math.roundToInt

@SuppressLint("ViewConstructor")
internal class NativeSettingsView(
    private val activity: Activity,
    private val onRefreshData: () -> Unit,
    private val onAppearanceChanged: () -> Unit,
    private val onNotificationPreferenceEnabled: () -> Unit,
    private val onPreferencesChanged: () -> Unit,
    private val onOpenPrivacy: () -> Unit,
    private val onOpenSupport: () -> Unit
) : ScrollView(activity) {
    private val preferences = activity.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val notificationStatus = TextView(activity)
    private val primaryTextViews = mutableListOf<TextView>()
    private val secondaryTextViews = mutableListOf<TextView>()
    private val cardViews = mutableListOf<View>()

    init {
        setBackgroundColor(NativePalette.background)
        isFillViewport = true

        val content = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(20), dp(16), dp(28))
        }
        addView(content, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        content.addView(title("Ajustes"))
        content.addView(sectionTitle("Notificações"))
        content.addView(
            description("Escolha os alertas do Palmeiras Agenda. A permissão do sistema é solicitada quando um alerta é ativado.")
        )
        content.addView(card(LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            addView(notificationSwitch("Lembrete 1 hora antes", KEY_ONE_HOUR, false))
            addView(notificationSwitch("Aviso no início do jogo", KEY_KICKOFF, false))
            addView(notificationSwitch("Placar final", KEY_RESULTS, false))
            addView(notificationSwitch("Mudanças de data e horário", KEY_SCHEDULE_CHANGES, false))
            addView(notificationSwitch("Gols e lances ao vivo", KEY_LIVE_EVENTS, false))
            addView(notificationSwitch("Notícias importantes", KEY_NEWS, false))
        }))
        notificationStatus.apply {
            textSize = 12f
            setTextColor(NativePalette.muted)
            setPadding(dp(4), dp(8), dp(4), 0)
        }
        secondaryTextViews += notificationStatus
        content.addView(notificationStatus)

        content.addView(sectionTitle("Time e privacidade"))
        content.addView(card(teamScopeControl()))
        content.addView(card(LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            addView(preferenceSwitch("Modo sem spoilers", KEY_SPOILER_FREE, false))
        }))

        content.addView(sectionTitle("Aparência"))
        content.addView(card(appearanceControl()))

        content.addView(sectionTitle("Dados"))
        content.addView(actionButton("Atualizar dados agora") { onRefreshData() })

        content.addView(sectionTitle("Aplicativo"))
        content.addView(card(LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            addView(infoRow("Versão", ApiConfig.APP_VERSION))
            addView(infoRow("Fonte", "Palmeiras Agenda"))
        }))
        content.addView(actionButton("Política de Privacidade", onOpenPrivacy))
        content.addView(actionButton("Suporte", onOpenSupport))

        refreshNotificationStatus()
    }

    fun setDarkMode(enabled: Boolean) {
        setBackgroundColor(if (enabled) NativePalette.darkBackground else NativePalette.background)
        primaryTextViews.forEach {
            it.setTextColor(if (enabled) NativePalette.darkInk else NativePalette.ink)
        }
        secondaryTextViews.forEach {
            it.setTextColor(if (enabled) NativePalette.darkMuted else NativePalette.muted)
        }
        cardViews.forEach {
            it.background = cardBackground(enabled)
        }
    }

    fun refreshNotificationStatus() {
        notificationStatus.text = when {
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED ->
                "Permissão ainda não concedida."
            !(activity.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).areNotificationsEnabled() ->
                "Notificações desativadas nos ajustes do Android."
            else -> "Notificações autorizadas neste aparelho."
        }
    }

    private fun notificationSwitch(label: String, key: String, defaultValue: Boolean): View {
        return Switch(activity).apply {
            text = label
            textSize = 15f
            setTextColor(NativePalette.ink)
            minimumHeight = dp(48)
            setPadding(dp(12), dp(8), dp(12), dp(8))
            isChecked = preferences.getBoolean(key, defaultValue)
            setOnCheckedChangeListener { _, enabled ->
                preferences.edit().putBoolean(key, enabled).apply()
                if (enabled) onNotificationPreferenceEnabled()
                onPreferencesChanged()
            }
            primaryTextViews += this
        }
    }

    private fun preferenceSwitch(label: String, key: String, defaultValue: Boolean): View {
        return Switch(activity).apply {
            text = label
            textSize = 15f
            setTextColor(NativePalette.ink)
            minimumHeight = dp(48)
            setPadding(dp(12), dp(8), dp(12), dp(8))
            isChecked = preferences.getBoolean(key, defaultValue)
            setOnCheckedChangeListener { _, enabled ->
                preferences.edit().putBoolean(key, enabled).apply()
                onPreferencesChanged()
            }
            primaryTextViews += this
        }
    }

    private fun teamScopeControl(): View {
        val group = RadioGroup(activity).apply {
            orientation = RadioGroup.HORIZONTAL
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }
        val current = preferences.getString(KEY_TEAM_SCOPE, TEAM_MEN) ?: TEAM_MEN
        listOf(TEAM_MEN to "Masculino", TEAM_WOMEN to "Feminino").forEach { (value, label) ->
            group.addView(RadioButton(activity).apply {
                id = View.generateViewId()
                tag = value
                text = label
                textSize = 15f
                setTextColor(NativePalette.ink)
                isChecked = value == current
                primaryTextViews += this
            }, RadioGroup.LayoutParams(0, RadioGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        group.setOnCheckedChangeListener { radioGroup, checkedId ->
            val selected = radioGroup.findViewById<RadioButton>(checkedId)?.tag as? String ?: return@setOnCheckedChangeListener
            preferences.edit().putString(KEY_TEAM_SCOPE, selected).apply()
            onPreferencesChanged()
        }
        return group
    }

    private fun appearanceControl(): View {
        val group = RadioGroup(activity).apply {
            orientation = RadioGroup.VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }
        val values = listOf(
            APPEARANCE_SYSTEM to "Seguir o sistema",
            APPEARANCE_LIGHT to "Tema claro",
            APPEARANCE_DARK to "Tema escuro"
        )
        val current = preferences.getString(KEY_APPEARANCE, APPEARANCE_SYSTEM) ?: APPEARANCE_SYSTEM
        values.forEach { (value, label) ->
            group.addView(RadioButton(activity).apply {
                id = View.generateViewId()
                tag = value
                text = label
                textSize = 15f
                setTextColor(NativePalette.ink)
                isChecked = value == current
                primaryTextViews += this
            })
        }
        group.setOnCheckedChangeListener { radioGroup, checkedId ->
            val selected = radioGroup.findViewById<RadioButton>(checkedId)?.tag as? String ?: return@setOnCheckedChangeListener
            preferences.edit().putString(KEY_APPEARANCE, selected).apply()
            onAppearanceChanged()
        }
        return group
    }

    private fun actionButton(label: String, action: () -> Unit): View {
        return TextView(activity).apply {
            text = label
            textSize = 14f
            gravity = Gravity.CENTER
            minimumHeight = dp(48)
            setTextColor(android.graphics.Color.WHITE)
            background = GradientDrawable().apply {
                setColor(NativePalette.brand)
                cornerRadius = dp(6).toFloat()
            }
            isClickable = true
            isFocusable = true
            setOnClickListener { action() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(2)
                bottomMargin = dp(4)
            }
        }
    }

    private fun title(text: String): View = TextView(activity).apply {
        this.text = text
        textSize = 28f
        setTextColor(NativePalette.ink)
        setTypeface(typeface, Typeface.BOLD)
        setPadding(dp(4), dp(4), dp(4), dp(12))
        primaryTextViews += this
    }

    private fun sectionTitle(text: String): View = TextView(activity).apply {
        this.text = text.uppercase()
        textSize = 12f
        letterSpacing = 0.12f
        setTextColor(NativePalette.gold)
        setTypeface(typeface, Typeface.NORMAL)
        setPadding(dp(4), dp(24), dp(4), dp(8))
    }

    private fun description(text: String): View = TextView(activity).apply {
        this.text = text
        textSize = 13f
        setTextColor(NativePalette.muted)
        setPadding(dp(4), 0, dp(4), dp(10))
        secondaryTextViews += this
    }

    private fun infoRow(label: String, value: String): View = LinearLayout(activity).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = dp(48)
        setPadding(dp(12), dp(10), dp(12), dp(10))
        addView(TextView(activity).apply {
            text = label
            textSize = 15f
            setTextColor(NativePalette.ink)
            primaryTextViews += this
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        addView(TextView(activity).apply {
            text = value
            textSize = 14f
            setTextColor(NativePalette.muted)
            secondaryTextViews += this
        })
    }

    private fun card(content: View): View = LinearLayout(activity).apply {
        orientation = LinearLayout.VERTICAL
        background = cardBackground(false)
        addView(
            content,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            bottomMargin = dp(4)
        }
        cardViews += this
    }

    private fun cardBackground(darkMode: Boolean) = GradientDrawable().apply {
        setColor(if (darkMode) NativePalette.darkSurface else NativePalette.surface)
        setStroke(dp(1), if (darkMode) NativePalette.darkLine else NativePalette.line)
        cornerRadius = dp(8).toFloat()
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).roundToInt()

    internal companion object {
        const val PREFERENCES = "native_settings"
        const val KEY_APPEARANCE = "appearance"
        const val APPEARANCE_SYSTEM = "system"
        const val APPEARANCE_LIGHT = "light"
        const val APPEARANCE_DARK = "dark"
        const val KEY_TEAM_SCOPE = "team_scope"
        const val TEAM_MEN = "men"
        const val TEAM_WOMEN = "women"
        const val KEY_SPOILER_FREE = "spoiler_free"
        const val KEY_ONE_HOUR = "notify_one_hour"
        const val KEY_KICKOFF = "notify_kickoff"
        const val KEY_RESULTS = "notify_results"
        const val KEY_SCHEDULE_CHANGES = "notify_schedule_changes"
        const val KEY_LIVE_EVENTS = "notify_live_events"
        const val KEY_NEWS = "notify_news"
    }
}
