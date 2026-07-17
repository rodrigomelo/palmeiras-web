package com.palmeiras.agenda

data class CompetitionsResponse(
    val year: Int,
    val teamId: Int,
    val competitions: List<CompetitionSummary>
)

data class CompetitionSummary(
    val code: String,
    val name: String,
    val year: Int,
    val totalMatches: Int,
    val finished: Int,
    val upcoming: Int,
    val live: Int,
    val record: CompetitionRecord,
    val nextMatch: Match?,
    val lastMatch: Match?,
    val currentStage: String?,
    val standing: Standing?
)

data class CompetitionRecord(
    val played: Int,
    val wins: Int,
    val draws: Int,
    val losses: Int,
    val goalsFor: Int,
    val goalsAgainst: Int,
    val goalDifference: Int,
    val points: Int
)

data class Standing(
    val position: Int?,
    val teamId: Int?,
    val teamName: String?,
    val teamShort: String?,
    val playedGames: Int?,
    val points: Int?,
    val goalsFor: Int?,
    val goalsAgainst: Int?,
    val goalDifference: Int?
)

data class Match(
    val id: Int,
    val utcDate: String,
    val status: String,
    val matchday: Int?,
    val stage: String?,
    val venue: String?,
    val broadcast: String?,
    val homeTeam: Team,
    val awayTeam: Team,
    val competition: Competition,
    val score: Score,
    val homeScore: Int?,
    val awayScore: Int?
)

data class Team(
    val id: Int?,
    val name: String,
    val shortName: String?,
    val tla: String?,
    val crest: String?
)

data class Competition(
    val code: String?,
    val name: String?
)

data class Score(
    val fullTime: ScoreLine,
    val halfTime: ScoreLine?
)

data class ScoreLine(
    val home: Int?,
    val away: Int?
)
