# Palmeiras Data Repository
# Todos os dados encontrados, mesmo não estruturados

## Última atualização: 2026-03-24

---

## LIBERTADORES 2026

### Palmeiras - Grupo F
- Cerro Porteño (Paraguai)
- Junior Barranquilla (Colômbia)  
- Sporting Cristal (Peru)

### Data de início: 7-9 April 2026

### Jogos confirmados:
- Ida: Junior Barranquilla x Palmeiras (8 April)
- Volta: Palmeiras x Sporting Cristal (16 April)
- Ida: Cerro Porteño x Palmeiras (29 April)
- Volta: Sporting Cristal x Palmeiras (5 May)
- Ida: Palmeiras x Cerro Porteño (20 May)
- Volta: Palmeiras x Junior Barranquilla (28 May)

### Campanha 2025 (site oficial)
- Vice-campeão (4ª vez): 1961, 1968, 2000, 2025
- Perdeu para Boca Juniors nas penalidades
- 100% na fase de grupos
- Líder geral pela 6ª vez em 8 edições desde 2018
- Único clube a fechar fase de grupos 100% em mais de uma oportunidade

### Campanha 2024
- Eliminou nas oitavas pelo Botafogo
- 8 partidas: 4 vitórias, 3 empates, 1 derrota
- 17 gols marcados, 9 sofridos

### Títulos da Libertadores
- 1999 (primeiro título)
- 2020-2021 (bicampeonato consecutivo)
- 2020 final: venceu Santos 1-0 no Maracanã (gol de Breno Lopes nos acréscimos)
- 2021 final: venceu Santos 2-1

### Recordes
- 11 semifinais de Libertadores (recorde brasileiro)
- 4 semifinais seguidas (recorde brasileiro, igualou Santos 1962-1965)
- 17 oitavas de final consecutivas (recorde brasileiro, ao lado do Grêmio)
- 8 oitavas seguidas (recorde brasileiro)
- 48 confrontos eliminatórios na história: 32 vitórias

---

## COPA DO BRASIL 2026

### Palmeiras - Quinta Fase
- Adversário: Jacuipense-BA
- Formato: Mata-mata (ida e volta)

### Jogos:
- Ida: Palmeiras x Jacuipense-BA (Semana 22/04/2026) - Allianz Parque
- Volta: Jacuipense-BA x Palmeiras (Semana 13/05/2026) - Estádio de Jacuipense

---

## CAMPEONATO BRASILEIRO 2025/2026

### Classificação atual
- Posição: seguir do banco de dados (football-data.org)

---

## DADOS HISTÓRICOS (site oficial)

### Conquistas do Palmeiras
- Bicampeão Libertadores (1999, 2020-2021)
- Maior campeão do Brasil
- Único clube brasileiro com 8 oitavas seguidas na Libertadores
- Único clube a fechar fase de grupos 100% em mais de uma oportunidade

### Curiosidades
- 2025: Vice pelo Boca Juniors nas penalidades (4ª vez vice)
- 2022: Eliminou nas semifinais pelo Athletico-PR (arbitragem polêmica)
- 2021: Bicampeonato - mesma final contra Santos
- 2020: Primeiro título - gol de Breno Lopes aos 90+2

---

## FONTES UTILIZADAS

1. football-data.org (API) - Jogos e classificação BSA
2. ge.globo - Notícias
3. lance.com.br - Notícias  
4. wikipedia.org - Libertadores
5. palmeiras.com.br - Site oficial (conquistas históricas)
6. CBF - Copa do Brasil

---

## SCRAPERS IMPLEMENTADOS

| Fonte | Status | Observação |
|-------|--------|------------|
| football-data.org | ✅ FUNCIONANDO | API primária |
| ge.globo | ✅ FUNCIONANDO | News |
| lance.com.br | ✅ FUNCIONANDO | News |
| palmeiras.com.br | ✅ FUNCIONANDO | Dados históricos |
| wikipedia | ✅ FUNCIONANDO | Libertadores |
| SofaScore | ⚠️ PARCIAL | JS-rendered |
| FlashScore | ⚠️ PARCIAL | JS-rendered |
| API-Football | ⚠️ LIMITAÇÃO | Free tier sem dados 2025/2026 |

---

## NOTAS

- API-Football key: 48158f75c594d982460e550dca67eb84
- Limitação: free tier não fornece dados de temporadas atuais para Libertadores
- Scraping de sites com JS requer Selenium para extração completa
