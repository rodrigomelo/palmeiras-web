package com.palmeiras.agenda

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher
import android.webkit.DownloadListener
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import org.json.JSONObject
import kotlin.math.roundToInt

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var loadingPanel: View
    private lateinit var errorPanel: View
    private lateinit var statusBarScrim: View
    private lateinit var contentRoot: FrameLayout
    private lateinit var bottomBar: NativeBottomBar
    private lateinit var settingsView: NativeSettingsView
    private var selectedDestination = NativeDestination.HOME
    private var pendingWebTab = NativeDestination.HOME.webTab ?: "home"
    private var pendingMatchID: String? = null
    private var hasVisiblePage = false
    private val backInvokedCallback: OnBackInvokedCallback? = if (Build.VERSION.SDK_INT >= 33) {
        OnBackInvokedCallback(::handleBackNavigation)
    } else {
        null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val isDebuggable = applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        WebView.setWebContentsDebuggingEnabled(isDebuggable)
        pendingMatchID = intent.getStringExtra(NotificationSync.EXTRA_MATCH_ID)
        setContentView(buildContentView())
        configureWebView()
        NotificationSync.initialize(this)
        if (Build.VERSION.SDK_INT >= 33) {
            backInvokedCallback?.let {
                onBackInvokedDispatcher.registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    it
                )
            }
        }

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(initialWebURL())
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val matchID = intent.getStringExtra(NotificationSync.EXTRA_MATCH_ID) ?: return
        pendingMatchID = matchID
        selectedDestination = NativeDestination.HOME
        pendingWebTab = NativeDestination.HOME.webTab ?: "home"
        webView.visibility = View.VISIBLE
        settingsView.visibility = View.GONE
        webView.loadUrl("${ApiConfig.WEB_APP_URL}?match=${Uri.encode(matchID)}")
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    @SuppressLint("GestureBackNavigation")
    @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        handleBackNavigation()
    }

    private fun handleBackNavigation() {
        if (selectedDestination == NativeDestination.SETTINGS) {
            showDestination(NativeDestination.HOME)
        } else if (webView.canGoBack()) {
            webView.goBack()
        } else {
            finishAfterTransition()
        }
    }

    override fun onDestroy() {
        if (Build.VERSION.SDK_INT >= 33) {
            backInvokedCallback?.let(onBackInvokedDispatcher::unregisterOnBackInvokedCallback)
        }
        webView.apply {
            stopLoading()
            loadUrl("about:blank")
            clearHistory()
            removeAllViews()
            destroy()
        }
        super.onDestroy()
    }

    private fun buildContentView(): View {
        val root = FrameLayout(this).apply {
            setBackgroundColor(BACKGROUND)
        }
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BACKGROUND)
        }
        root.addView(
            shell,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        contentRoot = FrameLayout(this).apply {
            setBackgroundColor(BACKGROUND)
        }
        shell.addView(
            contentRoot,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
            )
        )

        webView = WebView(this).apply {
            setBackgroundColor(BACKGROUND)
            isHorizontalScrollBarEnabled = false
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }
        contentRoot.addView(webView)

        statusBarScrim = View(this).apply {
            setBackgroundColor(BRAND)
        }
        contentRoot.addView(
            statusBarScrim,
            FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, 0, Gravity.TOP)
        )

        loadingPanel = buildLoadingPanel()
        contentRoot.addView(
            loadingPanel,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        errorPanel = buildErrorPanel()
        contentRoot.addView(
            errorPanel,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER
            ).apply {
                marginStart = dp(24)
                marginEnd = dp(24)
            }
        )

        settingsView = NativeSettingsView(
            activity = this,
            onRefreshData = {
                webView.evaluateJavascript("window.refreshAllData?.()", null)
                NotificationSync.synchronizeAsync(this)
                showDestination(NativeDestination.HOME)
            },
            onAppearanceChanged = ::applyNativeTheme,
            onNotificationPreferenceEnabled = ::ensureNotificationPermission,
            onPreferencesChanged = {
                applyNativeWebState()
                NotificationSync.synchronizeAsync(this)
            },
            onOpenPrivacy = { openExternal(Uri.parse(ApiConfig.PRIVACY_URL)) },
            onOpenSupport = { openExternal(Uri.parse(ApiConfig.SUPPORT_URL)) }
        ).apply {
            visibility = View.GONE
        }
        contentRoot.addView(
            settingsView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        bottomBar = NativeBottomBar(this, ::showDestination)
        bottomBar.visibility = View.GONE
        shell.addView(
            bottomBar,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        applySystemBarInsets(root)

        return root
    }

    @Suppress("DEPRECATION")
    private fun applySystemBarInsets(root: FrameLayout) {
        root.setOnApplyWindowInsetsListener { _, insets ->
            val topInset: Int
            val bottomInset: Int
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                topInset = insets.getInsets(WindowInsets.Type.statusBars()).top
                bottomInset = insets.getInsets(WindowInsets.Type.navigationBars()).bottom
            } else {
                topInset = insets.systemWindowInsetTop
                bottomInset = insets.systemWindowInsetBottom
            }

            (webView.layoutParams as FrameLayout.LayoutParams).apply {
                topMargin = topInset
                bottomMargin = 0
                webView.layoutParams = this
            }
            (settingsView.layoutParams as FrameLayout.LayoutParams).apply {
                topMargin = topInset
                settingsView.layoutParams = this
            }
            (statusBarScrim.layoutParams as FrameLayout.LayoutParams).apply {
                height = topInset
                statusBarScrim.layoutParams = this
            }
            bottomBar.setNavigationInset(bottomInset)
            insets
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        // The product is a first-party web application that requires JavaScript.
        // Navigation below keeps only the configured HTTPS host inside WebView.
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
            setSupportMultipleWindows(false)
            useWideViewPort = false
            loadWithOverviewMode = false
            userAgentString = "$userAgentString PalmeirasAgendaAndroid/${ApiConfig.APP_VERSION}"
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                loadingPanel.visibility = if (
                    newProgress < 100 && !hasVisiblePage && errorPanel.visibility != View.VISIBLE
                ) {
                    View.VISIBLE
                } else {
                    View.GONE
                }
            }
        }

        webView.addJavascriptInterface(NativeWebBridge(), "PalmeirasNative")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest): Boolean {
                return openOutsideAppIfNeeded(request.url)
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                hasVisiblePage = false
                errorPanel.visibility = View.GONE
                loadingPanel.visibility = View.VISIBLE
                bottomBar.visibility = View.GONE
            }

            override fun onPageCommitVisible(view: WebView?, url: String?) {
                hasVisiblePage = true
                loadingPanel.visibility = View.GONE
                revealBottomBar()
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                hasVisiblePage = true
                loadingPanel.visibility = View.GONE
                revealBottomBar()
                applyNativeWebState()
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                if (request.isForMainFrame) showError()
            }
        }

        webView.setDownloadListener(DownloadListener { url, _, _, _, _ ->
            openExternal(Uri.parse(url))
        })
    }

    private fun buildErrorPanel(): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(24), dp(24), dp(24))
            background = GradientDrawable().apply {
                setColor(NativePalette.surface)
                setStroke(dp(1), NativePalette.line)
                cornerRadius = dp(12).toFloat()
            }
            elevation = dp(4).toFloat()
            visibility = View.GONE

            addView(ImageView(this@MainActivity).apply {
                setImageResource(R.drawable.palmeiras_agenda_logo)
                scaleType = ImageView.ScaleType.CENTER_INSIDE
                background = GradientDrawable().apply {
                    setColor(NativePalette.brandStrong)
                    cornerRadius = dp(8).toFloat()
                }
                setPadding(dp(8), dp(8), dp(8), dp(8))
            }, LinearLayout.LayoutParams(dp(72), dp(72)).apply {
                bottomMargin = dp(12)
            })
            addView(TextView(this@MainActivity).apply {
                text = getString(R.string.load_error_title)
                textSize = 19f
                gravity = Gravity.CENTER
                setTextColor(INK)
                setTypeface(typeface, android.graphics.Typeface.BOLD)
            })
            addView(TextView(this@MainActivity).apply {
                text = getString(R.string.load_error_message)
                textSize = 14f
                gravity = Gravity.CENTER
                setTextColor(TEXT_MUTED)
                setPadding(0, dp(10), 0, dp(16))
            })
            addView(Button(this@MainActivity).apply {
                text = getString(R.string.retry)
                isAllCaps = false
                minimumHeight = dp(48)
                setTextColor(Color.WHITE)
                background = GradientDrawable().apply {
                    setColor(BRAND)
                    cornerRadius = dp(6).toFloat()
                }
                setOnClickListener {
                    errorPanel.visibility = View.GONE
                    loadingPanel.visibility = View.VISIBLE
                    bottomBar.visibility = View.GONE
                    webView.reload()
                }
            })
        }
    }

    private fun buildLoadingPanel(): View {
        return FrameLayout(this).apply {
            background = getDrawable(R.drawable.ic_launcher_background)
            contentDescription = getString(R.string.loading_content_description)

            val content = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                addView(ImageView(this@MainActivity).apply {
                    setImageResource(R.drawable.palmeiras_agenda_logo)
                    scaleType = ImageView.ScaleType.CENTER_INSIDE
                }, LinearLayout.LayoutParams(dp(112), dp(112)))
                addView(TextView(this@MainActivity).apply {
                    text = getString(R.string.app_name)
                    textSize = 24f
                    gravity = Gravity.CENTER
                    setTextColor(NativePalette.surface)
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                    setPadding(0, dp(8), 0, 0)
                })
                addView(TextView(this@MainActivity).apply {
                    text = getString(R.string.app_tagline)
                    textSize = 11f
                    letterSpacing = 0.16f
                    gravity = Gravity.CENTER
                    setTextColor(Color.argb(190, 255, 253, 243))
                    setPadding(0, dp(4), 0, dp(12))
                })
                progressBar = ProgressBar(this@MainActivity).apply {
                    isIndeterminate = true
                    indeterminateTintList = ColorStateList.valueOf(NativePalette.gold)
                }
                addView(progressBar, LinearLayout.LayoutParams(dp(36), dp(36)))
            }
            addView(
                content,
                FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    Gravity.CENTER
                )
            )
        }
    }

    private fun openOutsideAppIfNeeded(uri: Uri): Boolean {
        val scheme = uri.scheme?.lowercase()
        val isWeb = scheme == "http" || scheme == "https"
        val isInternal = isWeb && uri.host == ApiConfig.WEB_APP_HOST
        val isCalendarDownload = uri.path?.endsWith(".ics") == true

        if (isInternal && !isCalendarDownload) return false
        return openExternal(uri)
    }

    private fun openExternal(uri: Uri): Boolean {
        return try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
            true
        } catch (_: ActivityNotFoundException) {
            false
        }
    }

    private fun showError() {
        hasVisiblePage = false
        loadingPanel.visibility = View.GONE
        revealBottomBar()
        errorPanel.visibility = View.VISIBLE
    }

    private fun revealBottomBar() {
        bottomBar.visibility = View.VISIBLE
        // WebView can complete its first hardware-accelerated frame while this
        // sibling is still GONE. Refresh the selected state on the next frame
        // so every tab is painted immediately, not only after user input.
        bottomBar.post {
            bottomBar.setSelected(selectedDestination)
            bottomBar.requestLayout()
            bottomBar.invalidate()
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    private fun showDestination(destination: NativeDestination) {
        selectedDestination = destination
        bottomBar.setSelected(destination)

        val webTab = destination.webTab
        if (webTab == null) {
            webView.visibility = View.INVISIBLE
            loadingPanel.visibility = View.GONE
            errorPanel.visibility = View.GONE
            settingsView.refreshNotificationStatus()
            settingsView.visibility = View.VISIBLE
            return
        }

        pendingWebTab = webTab
        settingsView.visibility = View.GONE
        webView.visibility = View.VISIBLE
        webView.evaluateJavascript("window.nativeSelectTab?.('$webTab')", null)
    }

    private fun applyNativeWebState() {
        val preferences = getSharedPreferences(NativeSettingsView.PREFERENCES, MODE_PRIVATE)
        val scope = if (
            preferences.getString(NativeSettingsView.KEY_TEAM_SCOPE, NativeSettingsView.TEAM_MEN) == NativeSettingsView.TEAM_WOMEN
        ) NativeSettingsView.TEAM_WOMEN else NativeSettingsView.TEAM_MEN
        val spoiler = preferences.getBoolean(NativeSettingsView.KEY_SPOILER_FREE, false)
        val spoilerValue = if (spoiler) "true" else "false"
        val script = """
            (() => {
              let changed = false;
              if (localStorage.getItem('pa-team-scope') !== '$scope') {
                localStorage.setItem('pa-team-scope', '$scope'); changed = true;
              }
              if (localStorage.getItem('pa-spoiler-free') !== '$spoilerValue') {
                localStorage.setItem('pa-spoiler-free', '$spoilerValue'); changed = true;
              }
              if (changed) location.reload(); else window.nativeSelectTab?.('$pendingWebTab');
            })()
        """.trimIndent()
        webView.evaluateJavascript(script, null)
        applyNativeTheme()
        syncNativeNotificationStateToWeb()
    }

    private fun nativeNotificationState(): JSONObject {
        val preferences = getSharedPreferences(NativeSettingsView.PREFERENCES, MODE_PRIVATE)
        val prefKeys = listOf(
            NativeSettingsView.KEY_ONE_HOUR to "oneHour",
            NativeSettingsView.KEY_KICKOFF to "kickoff",
            NativeSettingsView.KEY_RESULTS to "results",
            NativeSettingsView.KEY_SCHEDULE_CHANGES to "scheduleChanges",
            NativeSettingsView.KEY_LIVE_EVENTS to "liveEvents",
            NativeSettingsView.KEY_NEWS to "news"
        )
        val preferencesEnabled = prefKeys.any { preferences.getBoolean(it.first, false) }
        val permissionGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        val systemEnabled =
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).areNotificationsEnabled()
        val authorized = permissionGranted && systemEnabled
        val permission = when {
            authorized -> "authorized"
            !preferencesEnabled -> "notDetermined"
            else -> "denied"
        }
        val prefsJson = JSONObject()
        for ((nativeKey, webKey) in prefKeys) {
            prefsJson.put(webKey, preferences.getBoolean(nativeKey, false))
        }
        return JSONObject()
            .put("active", preferencesEnabled && authorized)
            .put("permission", permission)
            .put("preferences", prefsJson)
    }

    private fun setAllNotificationPreferences(enabled: Boolean) {
        val preferences = getSharedPreferences(NativeSettingsView.PREFERENCES, MODE_PRIVATE)
        preferences.edit().apply {
            for (key in listOf(
                NativeSettingsView.KEY_ONE_HOUR,
                NativeSettingsView.KEY_KICKOFF,
                NativeSettingsView.KEY_RESULTS,
                NativeSettingsView.KEY_SCHEDULE_CHANGES,
                NativeSettingsView.KEY_LIVE_EVENTS,
                NativeSettingsView.KEY_NEWS
            )) {
                putBoolean(key, enabled)
            }
        }.apply()
        settingsView.refreshNotificationStatus()
        if (enabled) ensureNotificationPermission()
        syncNativeNotificationStateToWeb()
        NotificationSync.synchronizeAsync(this)
    }

    private fun syncNativeNotificationStateToWeb() {
        if (!::webView.isInitialized) return
        val payload = nativeNotificationState().toString()
        webView.evaluateJavascript(
            "window.PalmeirasFeatures?.setNativeNotificationState($payload)",
            null
        )
    }

    private inner class NativeWebBridge {
        @JavascriptInterface
        fun getNotificationState(): String = nativeNotificationState().toString()

        @JavascriptInterface
        fun openNotificationSettings() {
            runOnUiThread { showDestination(NativeDestination.SETTINGS) }
        }

        @JavascriptInterface
        fun toggleNotifications(enable: Boolean) {
            runOnUiThread { setAllNotificationPreferences(enable) }
        }
    }

    private fun initialWebURL(): String {
        val matchID = pendingMatchID ?: return ApiConfig.WEB_APP_URL
        return "${ApiConfig.WEB_APP_URL}?match=${Uri.encode(matchID)}"
    }

    private fun applyNativeTheme() {
        val preferences = getSharedPreferences(NativeSettingsView.PREFERENCES, MODE_PRIVATE)
        val appearance = preferences.getString(
            NativeSettingsView.KEY_APPEARANCE,
            NativeSettingsView.APPEARANCE_SYSTEM
        ) ?: NativeSettingsView.APPEARANCE_SYSTEM
        val systemDark = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
            Configuration.UI_MODE_NIGHT_YES
        val theme = when (appearance) {
            NativeSettingsView.APPEARANCE_DARK -> "dark"
            NativeSettingsView.APPEARANCE_LIGHT -> "light"
            else -> if (systemDark) "dark" else "light"
        }
        val darkMode = theme == "dark"
        settingsView.setDarkMode(darkMode)
        bottomBar.setDarkMode(darkMode)
        webView.evaluateJavascript("window.nativeSetTheme?.('$theme')", null)
    }

    private fun ensureNotificationPermission() {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                NOTIFICATION_PERMISSION_REQUEST
            )
        } else {
            settingsView.refreshNotificationStatus()
            syncNativeNotificationStateToWeb()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == NOTIFICATION_PERMISSION_REQUEST) {
            settingsView.refreshNotificationStatus()
            syncNativeNotificationStateToWeb()
        }
    }

    override fun onResume() {
        super.onResume()
        if (::settingsView.isInitialized) settingsView.refreshNotificationStatus()
        syncNativeNotificationStateToWeb()
    }

    private companion object {
        const val NOTIFICATION_PERMISSION_REQUEST = 4901
        val BRAND = Color.rgb(7, 92, 59)
        val BACKGROUND = Color.rgb(243, 245, 239)
        val INK = Color.rgb(16, 35, 26)
        val TEXT_MUTED = Color.rgb(97, 114, 103)
    }
}
