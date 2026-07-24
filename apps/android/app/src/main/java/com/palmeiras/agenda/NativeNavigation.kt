package com.palmeiras.agenda

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.roundToInt

internal object NativePalette {
    val brand = Color.rgb(7, 92, 59)
    val brandBright = Color.rgb(10, 122, 74)
    val brandStrong = Color.rgb(4, 53, 34)
    val brandSoft = Color.rgb(231, 241, 233)
    val gold = Color.rgb(201, 154, 61)
    val background = Color.rgb(243, 245, 239)
    val surface = Color.rgb(255, 253, 243)
    val ink = Color.rgb(16, 35, 26)
    val muted = Color.rgb(74, 93, 83)
    val line = Color.argb(26, 16, 35, 26)
    val darkBackground = Color.rgb(7, 17, 12)
    val darkSurface = Color.rgb(15, 30, 22)
    val darkInk = Color.rgb(239, 246, 241)
    val darkMuted = Color.rgb(179, 194, 185)
    val darkLine = Color.argb(31, 239, 246, 241)
    val red = Color.rgb(185, 59, 54)
}

internal enum class NativeIcon { AGENDA, TABLE, STATS, HISTORY, SETTINGS }

internal enum class NativeDestination(
    val label: String,
    val icon: NativeIcon,
    val webTab: String?
) {
    HOME("Agenda", NativeIcon.AGENDA, "home"),
    STANDINGS("Tabelas", NativeIcon.TABLE, "classificacao"),
    STATISTICS("Estatísticas", NativeIcon.STATS, "estatisticas"),
    HISTORY("Histórico", NativeIcon.HISTORY, "historico"),
    SETTINGS("Ajustes", NativeIcon.SETTINGS, null)
}

@SuppressLint("ViewConstructor")
internal class NativeNavIconView(
    context: Context,
    private val icon: NativeIcon
) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        // Coordinates below use a 24-point logical canvas. The canvas itself is
        // density-scaled in onDraw, so the stroke must remain in logical units.
        strokeWidth = 1.5f
        strokeCap = Paint.Cap.BUTT
        strokeJoin = Paint.Join.MITER
        color = NativePalette.muted
    }

    fun setIconColor(color: Int) {
        paint.color = color
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val scale = minOf(width, height) / 24f
        canvas.save()
        canvas.translate((width - 24f * scale) / 2f, (height - 24f * scale) / 2f)
        canvas.scale(scale, scale)
        when (icon) {
            NativeIcon.AGENDA -> drawAgenda(canvas)
            NativeIcon.TABLE -> drawTable(canvas)
            NativeIcon.STATS -> drawStats(canvas)
            NativeIcon.HISTORY -> drawHistory(canvas)
            NativeIcon.SETTINGS -> drawSettings(canvas)
        }
        canvas.restore()
    }

    private fun drawAgenda(canvas: Canvas) {
        canvas.drawRoundRect(RectF(4f, 5f, 20f, 20f), 1.5f, 1.5f, paint)
        canvas.drawLine(8f, 3f, 8f, 8f, paint)
        canvas.drawLine(16f, 3f, 16f, 8f, paint)
        canvas.drawLine(6f, 12f, 18f, 12f, paint)
        canvas.drawCircle(12f, 12f, 2.4f, paint)
    }

    private fun drawTable(canvas: Canvas) {
        for (row in 0..2) {
            val y = 6f + row * 6f
            canvas.drawRect(4f, y - 1.5f, 7f, y + 1.5f, paint)
            canvas.drawLine(10f, y, 20f, y, paint)
        }
    }

    private fun drawStats(canvas: Canvas) {
        canvas.drawLine(4f, 20f, 20f, 20f, paint)
        canvas.drawRect(5f, 13f, 8f, 20f, paint)
        canvas.drawRect(10.5f, 9f, 13.5f, 20f, paint)
        canvas.drawRect(16f, 4f, 19f, 20f, paint)
    }

    private fun drawHistory(canvas: Canvas) {
        canvas.drawCircle(12f, 12f, 8f, paint)
        canvas.drawLine(12f, 7f, 12f, 12f, paint)
        canvas.drawLine(12f, 12f, 16f, 14f, paint)
        canvas.drawLine(4f, 6f, 4f, 11f, paint)
        canvas.drawLine(4f, 6f, 9f, 6f, paint)
    }

    private fun drawSettings(canvas: Canvas) {
        canvas.drawCircle(12f, 12f, 3f, paint)
        canvas.drawCircle(12f, 12f, 7f, paint)
        for (index in 0 until 8) {
            val angle = Math.toRadians((index * 45).toDouble())
            val x1 = 12f + (8f * kotlin.math.cos(angle)).toFloat()
            val y1 = 12f + (8f * kotlin.math.sin(angle)).toFloat()
            val x2 = 12f + (10f * kotlin.math.cos(angle)).toFloat()
            val y2 = 12f + (10f * kotlin.math.sin(angle)).toFloat()
            canvas.drawLine(x1, y1, x2, y2, paint)
        }
    }

}

@SuppressLint("ViewConstructor")
internal class NativeBottomBar(
    context: Context,
    private val onSelected: (NativeDestination) -> Unit
) : LinearLayout(context) {
    private data class Item(
        val container: LinearLayout,
        val indicator: View,
        val icon: NativeNavIconView,
        val label: TextView
    )

    private val items = mutableMapOf<NativeDestination, Item>()
    private val baseBottomPadding = dp(7)
    private var selectedDestination = NativeDestination.HOME
    private var darkMode = false

    init {
        orientation = HORIZONTAL
        gravity = Gravity.CENTER
        setBackgroundColor(NativePalette.surface)
        elevation = 0f
        background = GradientDrawable().apply {
            setColor(NativePalette.surface)
            setStroke(dp(1), NativePalette.line)
        }
        setPadding(dp(4), 0, dp(4), baseBottomPadding)

        NativeDestination.entries.forEach { destination ->
            val indicator = View(context).apply {
                setBackgroundColor(Color.TRANSPARENT)
            }
            val icon = NativeNavIconView(context, destination.icon)
            val label = TextView(context).apply {
                text = destination.label
                textSize = 10f
                gravity = Gravity.CENTER
                maxLines = 1
                includeFontPadding = false
                setTypeface(typeface, Typeface.NORMAL)
            }
            val item = LinearLayout(context).apply {
                orientation = VERTICAL
                gravity = Gravity.CENTER
                minimumHeight = dp(56)
                setPadding(dp(2), 0, dp(2), dp(4))
                contentDescription = destination.label
                isClickable = true
                isFocusable = true
                addView(indicator, LayoutParams(dp(32), dp(2)))
                addView(icon, LayoutParams(dp(24), dp(24)))
                addView(label, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
                setOnClickListener { onSelected(destination) }
            }
            addView(item, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
            items[destination] = Item(item, indicator, icon, label)
        }

        setSelected(NativeDestination.HOME)
    }

    fun setSelected(destination: NativeDestination) {
        selectedDestination = destination
        items.forEach { (itemDestination, item) ->
            val selected = itemDestination == destination
            val color = if (selected) {
                NativePalette.brandBright
            } else if (darkMode) {
                NativePalette.darkMuted
            } else {
                NativePalette.muted
            }
            item.icon.setIconColor(color)
            item.label.setTextColor(color)
            item.container.isSelected = selected
            item.indicator.setBackgroundColor(if (selected) NativePalette.gold else Color.TRANSPARENT)
            item.container.background = null
            item.container.accessibilityLiveRegion = if (selected) {
                View.ACCESSIBILITY_LIVE_REGION_POLITE
            } else {
                View.ACCESSIBILITY_LIVE_REGION_NONE
            }
        }
    }

    fun setDarkMode(enabled: Boolean) {
        darkMode = enabled
        background = GradientDrawable().apply {
            setColor(if (enabled) NativePalette.darkSurface else NativePalette.surface)
            setStroke(dp(1), if (enabled) NativePalette.darkLine else NativePalette.line)
        }
        setSelected(selectedDestination)
    }

    fun setNavigationInset(bottomInset: Int) {
        setPadding(paddingLeft, paddingTop, paddingRight, baseBottomPadding + bottomInset)
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).roundToInt()
}
