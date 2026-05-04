# Knowledge Base Setup

All endpoints require: `X-Dashboard-Key: YOUR_KEY` header.

## Method 1: Q&A Pairs (recommended — exact answers, highest priority)

```bash
# Single pair
curl -X POST https://your-server-b/api/knowledge/add-qa \
  -H "X-Dashboard-Key: YOUR_KEY" \
  -F "question=Rücksendeadresse" \
  -F "answer=Muster GmbH · Musterstraße 1 · 12345 Berlin. Bitte Lieferschein beilegen."

# Bulk CSV import
curl -X POST https://your-server-b/api/knowledge/import-qa-csv \
  -H "X-Dashboard-Key: YOUR_KEY" \
  -F "file=@faq.csv"
```

**CSV format** (`question,answer` header row):
```csv
question,answer
Rücksendeadresse,Muster GmbH · Musterstraße 1 · 12345 Berlin. Bitte Lieferschein beilegen.
Wie lange dauert eine Rückerstattung?,Nach Eingang der Rücksendung erhalten Sie die Erstattung innerhalb von 5-7 Werktagen.
Kann ich ohne Rechnung umtauschen?,Ja – mit Ihrer Bestellnummer können wir den Kauf nachweisen.
Versandkostenfrei ab?,Versandkostenfrei ab einem Bestellwert von 49 €.
Wie lange habe ich Rückgaberecht?,Sie haben 30 Tage ab Lieferdatum um Artikel zurückzusenden.
Rücksendeetikett / Wer zahlt Rückversand?,Wir stellen ein kostenloses Rücksendeetikett per E-Mail bereit.
Wie lange Lieferzeit?,Standardlieferung 2-4 Werktage. Express 1-2 Werktage.
Welche Zahlungsarten gibt es?,PayPal, Kreditkarte, Klarna, Vorkasse und Rechnung (B2B).
```

## Method 2: Upload a Document

```bash
curl -X POST https://your-server-b/api/knowledge/upload \
  -H "X-Dashboard-Key: YOUR_KEY" \
  -F "file=@rueckgabebedingungen.pdf"
```
Supported: PDF, TXT, MD, DOCX (max 50 MB)

## Method 3: Crawl a URL

```bash
curl -X POST https://your-server-b/api/knowledge/add-url \
  -H "X-Dashboard-Key: YOUR_KEY" \
  -F "url=https://your-shop.de/hilfe/retouren"
```

## Method 4: Shopware CMS Sync

```bash
curl -X POST https://your-server-b/api/knowledge/sync-cms \
  -H "X-Dashboard-Key: YOUR_KEY"
```

## Check Status

```bash
curl https://your-server-b/api/knowledge/status \
  -H "X-Dashboard-Key: YOUR_KEY"
```

## Priority

Q&A pairs are checked **first** — if a match is found, RAG is skipped and the answer is returned directly. Use Q&A for anything with a definitive answer (addresses, timelines, policies).
