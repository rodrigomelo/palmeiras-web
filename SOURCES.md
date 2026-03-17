# Palmeiras Dashboard - Fontes de Dados

## Fontes de Dados

### Arquitetura de Fontes (v6)

```
┌─────────────────────────────────────────────────────────┐
│                    FONTES DE DADOS                       │
├─────────────────────────────────────────────────────────┤
│  PRIMÁRIA:                                              │
│  • football-data.org → Supabase → API → Frontend       │
│                                                         │
│  FALLBACK (Notícias):                                   │
│  • ge.globo (direto) → Frontend                        │
│                                                         │
│  O frontend NUNCA chama fontes externas diretamente.   │
│  Apenas o collector (cron) acessa APIs externas.       │
└─────────────────────────────────────────────────────────┘
```

### Fontes de Dados (Ordem de Confiabilidade)

| # | Fonte | Tipo | Confiabilidade | Função |
|---|-------|------|----------------|--------|
| 1 | **Supabase** | Database | ✅ Alta | Fonte principal (partidas, classificação) |
| 2 | **football-data.org** | API | Alta | Dados de partidas (via collector) |
| 3 | **ge.globo** | Fallback | Média | Notícias (se Supabase falhar) |
| 4 | **Lance!** | Portal de notícias | Alta | Backup notícias |
| 5 | **Transfermarkt** | Dados de mercado | Média | Elenco (futuro) |
| 6 | **Sofascore** | Estatísticas | Média | Estatísticas avançadas (futuro) |

### Detalhes das Fontes

#### 1. football-data.org
- **Tipo:** API REST
- **Dados:** Partidas, resultados, classificação, escalações
- **Plano:** Free tier (limitado)
- **Time ID:** 1769 (SE Palmeiras)

#### 2. ge.globo
- **Tipo:** Portal de notícias brasileiro
- **Dados:** Notícias, resultados, schedule
- **Disponibilidade:** Gratuito (requer scraping)

#### 3. Lance!
- **Tipo:** Portal de notícias esportivas
- **Dados:** Notícias, análises
- **Disponibilidade:** Gratuito

### Estádio

- **Nome:** Allianz Parque
- **Endereço:** Rua Palestra Itália, 200 - Água Branca, São Paulo, SP
- **Capacidade:** 43.713 lugares
- **Inauguração:** 19 de novembro de 2014

### Onde Assistir (TV/Streaming)

| Canal | Tipo |
|-------|------|
| TV Globo | Gratuito |
| SporTV | Pago |
| Premiere | PPV |
| Amazon Prime Video | Streaming |
| Globoplay | Streaming |

---

*Dados atualizados: 13/03/2026*
*Dashboard: Palmeiras VerdaoTracker v3*
