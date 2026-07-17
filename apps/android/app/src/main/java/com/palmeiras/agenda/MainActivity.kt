package com.palmeiras.agenda

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

class MainActivity : Activity() {
    private val apiClient = PalmeirasApiClient()
    private lateinit var content: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(AppColor.background)
        }
        root.addView(headerBand())

        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), 0, dp(16), dp(28))
        }
        root.addView(content)

        setContentView(
            ScrollView(this).apply {
                isFillViewport = true
                addView(root)
            }
        )

        loadDashboard()
    }

    private fun loadDashboard() {
        showLoading()
        Thread {
            try {
                val competitions = apiClient.competitionSummaries().competitions
                val matches = apiClient.upcomingPalmeirasMatches()
                runOnUiThread { renderDashboard(competitions, matches) }
            } catch (error: Exception) {
                runOnUiThread { showError() }
            }
        }.start()
    }

    private fun renderDashboard(competitions: List<CompetitionSummary>, matches: List<Match>) {
        content.removeAllViews()
        content.addView(matchHero(matches.firstOrNull() ?: competitions.firstNotNullOfOrNull { it.nextMatch }))
        content.addView(competitionSection(competitions))
        content.addView(upcomingSection(matches))
    }

    private fun showLoading() {
        content.removeAllViews()
        content.addView(
            appCard().apply {
                addView(text("Carregando Palmeiras Agenda", 18f, AppColor.ink, Typeface.BOLD).apply {
                    gravity = Gravity.CENTER
                })
                addView(text("Buscando jogos, disputas e calendário.", 13f, AppColor.textMuted, Typeface.BOLD).apply {
                    gravity = Gravity.CENTER
                    setPadding(0, dp(8), 0, 0)
                })
            }
        )
    }

    private fun showError() {
        content.removeAllViews()
        content.addView(
            appCard().apply {
                addView(text("Erro ao carregar", 20f, AppColor.ink, Typeface.BOLD).apply {
                    gravity = Gravity.CENTER
                })
                addView(text("Não foi possível acessar o backend compartilhado.", 13f, AppColor.textMuted, Typeface.BOLD).apply {
                    gravity = Gravity.CENTER
                    setPadding(0, dp(8), 0, dp(14))
                })
                addView(Button(this@MainActivity).apply {
                    text = "Tentar novamente"
                    textSize = 14f
                    setTypeface(typeface, Typeface.BOLD)
                    setTextColor(AppColor.onDark)
                    background = rounded(AppColor.brand, 6f)
                    setOnClickListener { loadDashboard() }
                })
            }
        )
    }

    private fun headerBand(): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.BOTTOM or Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(20), dp(18), dp(28))
            background = gradient(intArrayOf(AppColor.brandStrong, AppColor.brand, AppColor.headerDeep), 0f)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(148)
            )

            addView(paAgendaMark(dp(54)))
            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(14), 0, 0, 0)
                    addView(text("Palmeiras Agenda", 24f, AppColor.onDark, Typeface.BOLD))
                    addView(text("Agenda tática de jogos, desempenho e calendário", 13f, AppColor.onDarkMuted, Typeface.BOLD).apply {
                        setPadding(0, dp(4), 0, 0)
                    })
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            )
        }
    }

    private fun matchHero(match: Match?): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(18))
            background = gradient(intArrayOf(AppColor.brand, AppColor.brandBright, AppColor.brandStrong), 8f)
            elevation = dp(8).toFloat()
            layoutParams = spacedParams(top = -18, bottom = 14)

            addView(chip(match?.competition?.name ?: "Próximo jogo", AppColor.gold, AppColor.onDarkWash))

            if (match == null) {
                addView(text("Nenhum jogo agendado", 18f, AppColor.onDark, Typeface.BOLD).apply {
                    gravity = Gravity.CENTER
                    setPadding(0, dp(28), 0, dp(20))
                })
                return@apply
            }

            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER
                    setPadding(0, dp(22), 0, dp(18))
                    addView(teamColumn(teamName(match.homeTeam), match.homeTeam.id == 1769), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                    addView(text(scoreText(match), 31f, AppColor.onDark, Typeface.BOLD).apply {
                        gravity = Gravity.CENTER
                    }, LinearLayout.LayoutParams(dp(58), LinearLayout.LayoutParams.WRAP_CONTENT))
                    addView(teamColumn(teamName(match.awayTeam), match.awayTeam.id == 1769), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                }
            )

            addView(text(matchDateText(match.utcDate), 13f, AppColor.onDark, Typeface.BOLD).apply {
                gravity = Gravity.CENTER
            })
            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER
                    setPadding(0, dp(10), 0, 0)
                    addView(heroPill(match.venue ?: "Estádio a definir"))
                    addView(heroPill(match.broadcast ?: "TV a confirmar"))
                }
            )
        }
    }

    private fun competitionSection(competitions: List<CompetitionSummary>): View {
        return appCard().apply {
            addView(sectionHeader("Disputas do Palmeiras", "${competitions.size} competições consolidadas"))
            if (competitions.isEmpty()) {
                addView(emptyPanel("Nenhuma competição encontrada."))
            } else {
                competitions.forEach { competition ->
                    addView(competitionCard(competition))
                }
            }
        }
    }

    private fun competitionCard(competition: CompetitionSummary): View {
        val color = compColor(competition.code)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(14), dp(14), dp(14))
            background = rounded(tint(color, 0.10f), 8f, tint(color, 0.34f))
            layoutParams = spacedParams(top = 10)

            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.TOP
                    addView(
                        LinearLayout(this@MainActivity).apply {
                            orientation = LinearLayout.VERTICAL
                            addView(text(competition.code, 10f, color, Typeface.BOLD))
                            addView(text(displayCompetitionName(competition), 17f, AppColor.ink, Typeface.BOLD).apply {
                                setPadding(0, dp(4), 0, 0)
                            })
                        },
                        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                    )
                    addView(chip(competitionStatus(competition), statusColor(competition), tint(statusColor(competition), 0.13f)))
                }
            )

            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, dp(12), 0, dp(12))
                    addView(statTile("${competition.record.played}", "J"), weightParams())
                    addView(statTile("${competition.record.wins}", "V"), weightParams())
                    addView(statTile("${competition.record.draws}", "E"), weightParams())
                    addView(statTile("${competition.record.losses}", "D"), weightParams())
                    addView(statTile(performanceText(competition.record), "APR"), weightParams())
                }
            )

            (competition.nextMatch ?: competition.lastMatch)?.let { match ->
                addView(
                    LinearLayout(this@MainActivity).apply {
                        orientation = LinearLayout.VERTICAL
                        setPadding(dp(12), dp(12), dp(12), dp(12))
                        background = rounded(AppColor.surface, 6f, AppColor.line)
                        addView(text(if (competition.nextMatch == null) "Último" else "Próximo", 10f, AppColor.textMuted, Typeface.BOLD))
                        addView(text(matchTitle(match), 14f, AppColor.text, Typeface.BOLD).apply {
                            setPadding(0, dp(5), 0, dp(5))
                        })
                        addView(text(matchDateText(match.utcDate), 11f, color, Typeface.BOLD))
                    }
                )
            }
        }
    }

    private fun upcomingSection(matches: List<Match>): View {
        return appCard().apply {
            addView(sectionHeader("Próximos jogos", "Agenda imediata do Verdão"))
            if (matches.isEmpty()) {
                addView(emptyPanel("Nenhum jogo encontrado."))
            } else {
                matches.take(5).forEach { match ->
                    addView(upcomingRow(match))
                }
            }
        }
    }

    private fun upcomingRow(match: Match): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = rounded(AppColor.softSurface, 8f, AppColor.line)
            layoutParams = spacedParams(top = 8)

            addView(
                LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(text(match.competition.name ?: "Campeonato", 10f, compColor(match.competition.code ?: ""), Typeface.BOLD))
                    addView(text(matchTitle(match), 15f, AppColor.text, Typeface.BOLD).apply {
                        setPadding(0, dp(4), 0, dp(4))
                    })
                    addView(text(matchDateText(match.utcDate), 12f, AppColor.textMuted, Typeface.BOLD))
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            )
            addView(chip(if (match.status == "IN_PLAY") "AO VIVO" else "AGENDADO", AppColor.brand, AppColor.brandSoft))
        }
    }

    private fun sectionHeader(title: String, subtitle: String): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(text(title, 19f, AppColor.ink, Typeface.BOLD))
            addView(text(subtitle, 12f, AppColor.textMuted, Typeface.BOLD).apply {
                setPadding(0, dp(4), 0, dp(2))
            })
        }
    }

    private fun appCard(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(18))
            background = rounded(AppColor.surface, 8f, AppColor.line)
            elevation = dp(4).toFloat()
            layoutParams = spacedParams(bottom = 14)
        }
    }

    private fun emptyPanel(message: String): View {
        return text(message, 13f, AppColor.textMuted, Typeface.BOLD).apply {
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(18), dp(16), dp(18))
            background = rounded(AppColor.softSurface, 8f)
        }
    }

    private fun teamColumn(name: String, isPalmeiras: Boolean): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            addView(if (isPalmeiras) paAgendaMark(dp(52)) else unknownBadge(dp(52)))
            addView(text(name, 17f, AppColor.onDark, Typeface.BOLD).apply {
                gravity = Gravity.CENTER
                maxLines = 2
                setPadding(dp(4), dp(8), dp(4), 0)
            })
        }
    }

    private fun paAgendaMark(size: Int): View {
        return FrameLayout(this).apply {
            background = gradientStroke(
                intArrayOf(AppColor.brandBright, AppColor.brand, AppColor.brandStrong),
                size * 0.17f / resources.displayMetrics.density,
                AppColor.gold,
                3
            )
            layoutParams = LinearLayout.LayoutParams(size, size)

            addView(
                FrameLayout(this@MainActivity).apply {
                    background = rounded(AppColor.surface, 7f)

                    addView(
                        View(this@MainActivity).apply { background = rounded(AppColor.gold, 0f) },
                        FrameLayout.LayoutParams(
                            (size * 0.54f).roundToInt(),
                            (size * 0.13f).roundToInt(),
                            Gravity.TOP or Gravity.CENTER_HORIZONTAL
                        )
                    )

                    addView(
                        TextView(this@MainActivity).apply {
                            text = "PA"
                            gravity = Gravity.CENTER
                            textSize = (size / resources.displayMetrics.density) * 0.24f
                            setTypeface(typeface, Typeface.BOLD)
                            setTextColor(AppColor.ink)
                        },
                        FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT)
                    )
                },
                FrameLayout.LayoutParams(
                    (size * 0.54f).roundToInt(),
                    (size * 0.62f).roundToInt(),
                    Gravity.CENTER
                )
            )
        }
    }

    private fun unknownBadge(size: Int): View {
        return TextView(this).apply {
            text = "?"
            gravity = Gravity.CENTER
            textSize = 20f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(AppColor.textMuted)
            background = oval(AppColor.onDarkMuted)
            layoutParams = LinearLayout.LayoutParams(size, size)
        }
    }

    private fun statTile(value: String, label: String): View {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(4), dp(9), dp(4), dp(9))
            background = rounded(AppColor.surface, 6f, AppColor.line)
            addView(text(value, 15f, AppColor.ink, Typeface.BOLD).apply { gravity = Gravity.CENTER })
            addView(text(label, 9f, AppColor.textMuted, Typeface.BOLD).apply {
                gravity = Gravity.CENTER
                setPadding(0, dp(4), 0, 0)
            })
        }
    }

    private fun heroPill(value: String): View {
        return text(value, 11f, AppColor.onDarkMuted, Typeface.BOLD).apply {
            setPadding(dp(9), dp(6), dp(9), dp(6))
            background = rounded(AppColor.onDarkWash, 99f, AppColor.onDarkLine)
        }
    }

    private fun chip(value: String, textColor: Int, bgColor: Int): TextView {
        return text(value, 10f, textColor, Typeface.BOLD).apply {
            setPadding(dp(9), dp(6), dp(9), dp(6))
            background = rounded(bgColor, 99f)
        }
    }

    private fun text(value: String, size: Float, color: Int, style: Int): TextView {
        return TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            setTypeface(typeface, style)
            includeFontPadding = true
        }
    }

    private fun weightParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
            marginEnd = dp(6)
        }
    }

    private fun spacedParams(top: Int = 0, bottom: Int = 0): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = dp(top)
            bottomMargin = dp(bottom)
        }
    }

    private fun rounded(color: Int, radius: Float, strokeColor: Int? = null): GradientDrawable {
        return GradientDrawable().apply {
            setColor(color)
            cornerRadius = dp(radius).toFloat()
            strokeColor?.let { setStroke(dp(1), it) }
        }
    }

    private fun oval(color: Int, strokeColor: Int? = null, strokeWidth: Int = 0): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(color)
            strokeColor?.let { setStroke(dp(strokeWidth), it) }
        }
    }

    private fun gradient(colors: IntArray, radius: Float): GradientDrawable {
        return GradientDrawable(GradientDrawable.Orientation.TL_BR, colors).apply {
            cornerRadius = dp(radius).toFloat()
        }
    }

    private fun gradientStroke(colors: IntArray, radius: Float, strokeColor: Int, strokeWidth: Int): GradientDrawable {
        return GradientDrawable(GradientDrawable.Orientation.TL_BR, colors).apply {
            cornerRadius = dp(radius).toFloat()
            setStroke(dp(strokeWidth), strokeColor)
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    private fun dp(value: Float): Int = (value * resources.displayMetrics.density).roundToInt()

    private fun tint(color: Int, alpha: Float): Int {
        return Color.argb((alpha * 255).roundToInt(), Color.red(color), Color.green(color), Color.blue(color))
    }

    private fun teamName(team: Team): String = team.shortName ?: team.name

    private fun matchTitle(match: Match): String = "${teamName(match.homeTeam)} x ${teamName(match.awayTeam)}"

    private fun scoreText(match: Match): String {
        val home = match.homeScore
        val away = match.awayScore
        return if (home != null && away != null) "$home-$away" else "x"
    }

    private fun matchDateText(value: String): String {
        return try {
            val date = OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.of("America/Sao_Paulo"))
            date.format(DateTimeFormatter.ofPattern("dd/MM HH:mm"))
        } catch (error: Exception) {
            value
        }
    }

    private fun displayCompetitionName(competition: CompetitionSummary): String {
        return when (competition.code) {
            "BSA" -> "Brasileirão"
            "CLI" -> "Libertadores"
            "COPA" -> "Copa do Brasil"
            "CPA" -> "Paulistão"
            "WC" -> "Copa 2026"
            else -> competition.name
        }
    }

    private fun compColor(code: String): Int {
        return when (code) {
            "BSA" -> AppColor.brandBright
            "CLI" -> AppColor.gold
            "COPA" -> AppColor.blue
            "CPA" -> Color.rgb(107, 127, 50)
            "WC" -> Color.rgb(139, 63, 104)
            else -> AppColor.textMuted
        }
    }

    private fun competitionStatus(competition: CompetitionSummary): String {
        return when {
            competition.live > 0 -> "Ao vivo"
            competition.nextMatch != null -> "Em disputa"
            competition.finished == competition.totalMatches -> "Encerrada"
            else -> "Sem agenda"
        }
    }

    private fun statusColor(competition: CompetitionSummary): Int {
        return when {
            competition.live > 0 -> AppColor.live
            competition.nextMatch != null -> AppColor.brand
            else -> AppColor.textMuted
        }
    }

    private fun performanceText(record: CompetitionRecord): String {
        if (record.played <= 0) return "0%"
        val pct = (record.points.toDouble() / (record.played * 3).toDouble() * 100).roundToInt()
        return "$pct%"
    }
}

private object AppColor {
    val brand = Color.rgb(7, 92, 59)
    val brandStrong = Color.rgb(4, 53, 34)
    val brandBright = Color.rgb(10, 122, 74)
    val headerDeep = Color.rgb(17, 55, 38)
    val brandSoft = Color.rgb(231, 241, 233)
    val gold = Color.rgb(201, 154, 61)
    val blue = Color.rgb(36, 104, 168)
    val live = Color.rgb(185, 59, 54)
    val ink = Color.rgb(16, 35, 26)
    val text = Color.rgb(23, 37, 29)
    val textMuted = Color.rgb(97, 114, 103)
    val background = Color.rgb(243, 245, 239)
    val surface = Color.rgb(251, 252, 248)
    val softSurface = Color.rgb(233, 239, 232)
    val line = Color.rgb(217, 226, 216)
    val onDark = Color.rgb(250, 252, 248)
    val onDarkMuted = Color.argb(190, 250, 252, 248)
    val onDarkWash = Color.argb(28, 250, 252, 248)
    val onDarkLine = Color.argb(40, 250, 252, 248)
}
