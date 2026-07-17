package com.palmeiras.agenda

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class PalmeirasApiClient(
    private val baseUrl: String = ApiConfig.BASE_URL,
    private val fallbackBaseUrls: List<String> = listOf(ApiConfig.LEGACY_BASE_URL)
) {
    fun upcomingPalmeirasMatches(limit: Int = 5): List<Match> {
        val query = mapOf(
            "status" to "SCHEDULED,TIMED,IN_PLAY,PAUSED",
            "team_id" to "1769",
            "limit" to limit.toString()
        )
        return getMatches(query)
    }

    fun competitionSummaries(year: Int? = null): CompetitionsResponse {
        val query = mutableMapOf("team_id" to "1769")
        if (year != null) query["year"] = year.toString()

        val response = JSONObject(get("competitions", query))
        val competitions = response.getJSONArray("competitions")
        return CompetitionsResponse(
            year = response.getInt("year"),
            teamId = response.getInt("teamId"),
            competitions = (0 until competitions.length()).map { index ->
                parseCompetitionSummary(competitions.getJSONObject(index))
            }
        )
    }

    fun worldCupMatches(): List<Match> {
        val query = mapOf(
            "competition" to "WC",
            "from_date" to "2026-06-11",
            "to_date" to "2026-07-19",
            "limit" to "200"
        )
        return getMatches(query)
    }

    private fun getMatches(query: Map<String, String>): List<Match> {
        val response = get("matches", query)
        val matches = JSONObject(response).getJSONArray("matches")
        return (0 until matches.length()).map { index ->
            parseMatch(matches.getJSONObject(index))
        }
    }

    private fun get(path: String, query: Map<String, String>): String {
        var lastError: Exception? = null
        for (candidateBaseUrl in listOf(baseUrl) + fallbackBaseUrls) {
            try {
                return get(path, query, candidateBaseUrl)
            } catch (error: Exception) {
                lastError = error
            }
        }
        throw lastError ?: IllegalStateException("Unable to build Palmeiras API request")
    }

    private fun get(path: String, query: Map<String, String>, candidateBaseUrl: String): String {
        val encodedQuery = query.entries.joinToString("&") { (key, value) ->
            "${key.encode()}=${value.encode()}"
        }
        val querySuffix = if (encodedQuery.isBlank()) "" else "?$encodedQuery"
        val url = URL("${candidateBaseUrl.trimEnd('/')}/$path$querySuffix")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            setRequestProperty("Accept", "application/json")
            connectTimeout = 10_000
            readTimeout = 10_000
        }

        try {
            val status = connection.responseCode
            val stream = if (status in 200..299) {
                connection.inputStream
            } else {
                connection.errorStream ?: connection.inputStream
            }
            val body = stream.bufferedReader().use { it.readText() }
            if (status !in 200..299) {
                throw IllegalStateException("Backend returned HTTP $status: $body")
            }
            return body
        } finally {
            connection.disconnect()
        }
    }

    private fun parseTeam(json: JSONObject): Team {
        return Team(
            id = json.optNullableInt("id"),
            name = json.optString("name"),
            shortName = json.optString("shortName").ifBlank { null },
            tla = json.optString("tla").ifBlank { null },
            crest = json.optString("crest").ifBlank { null }
        )
    }

    private fun parseCompetition(json: JSONObject): Competition {
        return Competition(
            code = json.optString("code").ifBlank { null },
            name = json.optString("name").ifBlank { null }
        )
    }

    private fun parseCompetitionSummary(json: JSONObject): CompetitionSummary {
        return CompetitionSummary(
            code = json.getString("code"),
            name = json.getString("name"),
            year = json.getInt("year"),
            totalMatches = json.getInt("totalMatches"),
            finished = json.getInt("finished"),
            upcoming = json.getInt("upcoming"),
            live = json.getInt("live"),
            record = parseCompetitionRecord(json.getJSONObject("record")),
            nextMatch = json.optNullableObject("nextMatch")?.let(::parseMatch),
            lastMatch = json.optNullableObject("lastMatch")?.let(::parseMatch),
            currentStage = json.optString("currentStage").ifBlank { null },
            standing = json.optNullableObject("standing")?.let(::parseStanding)
        )
    }

    private fun parseCompetitionRecord(json: JSONObject): CompetitionRecord {
        return CompetitionRecord(
            played = json.getInt("played"),
            wins = json.getInt("wins"),
            draws = json.getInt("draws"),
            losses = json.getInt("losses"),
            goalsFor = json.getInt("goalsFor"),
            goalsAgainst = json.getInt("goalsAgainst"),
            goalDifference = json.getInt("goalDifference"),
            points = json.getInt("points")
        )
    }

    private fun parseStanding(json: JSONObject): Standing {
        return Standing(
            position = json.optNullableInt("position"),
            teamId = json.optNullableInt("teamId"),
            teamName = json.optString("teamName").ifBlank { null },
            teamShort = json.optString("teamShort").ifBlank { null },
            playedGames = json.optNullableInt("playedGames"),
            points = json.optNullableInt("points"),
            goalsFor = json.optNullableInt("goalsFor"),
            goalsAgainst = json.optNullableInt("goalsAgainst"),
            goalDifference = json.optNullableInt("goalDifference")
        )
    }

    private fun parseMatch(item: JSONObject): Match {
        return Match(
            id = item.getInt("id"),
            utcDate = item.getString("utcDate"),
            status = item.getString("status"),
            matchday = item.optNullableInt("matchday"),
            stage = item.optString("stage").ifBlank { null },
            venue = item.optString("venue").ifBlank { null },
            broadcast = item.optString("broadcast").ifBlank { null },
            homeTeam = parseTeam(item.getJSONObject("homeTeam")),
            awayTeam = parseTeam(item.getJSONObject("awayTeam")),
            competition = parseCompetition(item.getJSONObject("competition")),
            score = parseScore(item.optJSONObject("score")),
            homeScore = item.optNullableInt("homeScore"),
            awayScore = item.optNullableInt("awayScore")
        )
    }

    private fun parseScore(json: JSONObject?): Score {
        return Score(
            fullTime = parseScoreLine(json?.optJSONObject("fullTime")),
            halfTime = json?.optNullableObject("halfTime")?.let(::parseScoreLine)
        )
    }

    private fun parseScoreLine(json: JSONObject?): ScoreLine {
        return ScoreLine(
            home = json?.optNullableInt("home"),
            away = json?.optNullableInt("away")
        )
    }

    private fun String.encode(): String = URLEncoder.encode(this, Charsets.UTF_8.name())

    private fun JSONObject.optNullableInt(name: String): Int? {
        return if (isNull(name)) null else optInt(name)
    }

    private fun JSONObject.optNullableObject(name: String): JSONObject? {
        return if (isNull(name)) null else optJSONObject(name)
    }
}
