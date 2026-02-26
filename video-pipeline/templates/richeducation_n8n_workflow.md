# Rich Education — n8n Production Workflow

## Overview
```
[Form Trigger] → [Set Variables] → [Script Node] → [Visual Node] → [Thumbnail Node] → [Aggregate] → [Google Docs / Notion / Slack] → [Google Sheets]
```

Nodes 3, 4, 5 run in parallel. Connect all three from Node 2, merge into Node 6 using a Merge node set to "Wait for all inputs."

---

## Node 1 — Form Trigger
Type: n8n Form Trigger

Fields:
- topic (text) — e.g., "Abraham Lincoln"
- grade (text) — e.g., "8th grade"
- subject (text) — e.g., "U.S. History"
- video_title (text) — e.g., "Abraham Lincoln Explained for 8th Graders"

## Node 2 — Set Variables
Type: Set

```json
{
  "topic": "{{ $json.topic }}",
  "grade": "{{ $json.grade }}",
  "subject": "{{ $json.subject }}",
  "video_title": "{{ $json.video_title }}"
}
```

## Node 3 — Script Generator
Type: HTTP Request → Claude API (Anthropic)

- Method: POST
- URL: https://api.anthropic.com/v1/messages
- Headers:
  - x-api-key: YOUR_ANTHROPIC_KEY
  - anthropic-version: 2023-06-01
  - content-type: application/json

Body:
```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 2000,
  "messages": [
    {
      "role": "user",
      "content": "You are helping me write a YouTube script for K-12 students. The channel is called Rich Education and it is a faceless educational channel (voiceover + simple visuals only).\n\nWrite a detailed script (about 1,000-1,200 words) for a 5-8 minute video:\n\nVideo title: {{ $node['Set Variables'].json.video_title }}\nTopic: {{ $node['Set Variables'].json.topic }}\nGrade level: {{ $node['Set Variables'].json.grade }}\nSubject: {{ $node['Set Variables'].json.subject }}\n\nAudience and tone:\n- Talk directly to a student who just learned about this in school and is still confused.\n- Use simple, clear language, short sentences, everyday examples.\n- No slang, no baby talk, no textbook jargon.\n- Keep it 100% original.\n\nStructure:\n1. Hook (20-30 seconds) - confusion-to-clarity opener\n2. Early life or background (1 min)\n3. Path to the main problem or event (1 min)\n4. The big problem or conflict (1.5 min)\n5. Key actions or turning points (2 min)\n6. Impact and legacy (1 min)\n7. Recap + 5 check-yourself questions (45 sec)\n\nImportant: Keep all facts accurate for the grade level. No graphic content. End with an invitation to watch the next video in the playlist."
    }
  ]
}
```
Output: `$json.content[0].text`

## Node 4 — Visual Shot List Generator
Type: HTTP Request → Claude API

Same headers as Node 3.

Body:
```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 2000,
  "messages": [
    {
      "role": "user",
      "content": "You are helping produce visuals for a faceless YouTube channel called Rich Education, which makes K-12 explainer videos.\n\nGenerate a visual shot list for this video:\nTopic: {{ $node['Set Variables'].json.topic }}\nGrade: {{ $node['Set Variables'].json.grade }}\nSubject: {{ $node['Set Variables'].json.subject }}\n\nHere is the script to match visuals to:\n{{ $node['Script Generator'].json.content[0].text }}\n\nFor each section provide:\n1. Background\n2. Visual beats\n3. On-screen text (3-6 words max per phrase)\n4. Transition suggestion\n\nBrand rules:\n- Dark navy background (#1a1a2e)\n- Gold/yellow highlights (#f5c518) for key terms\n- White body text\n- Simple silhouette-style illustrations only, no real photos\n- Map-based visuals wherever geography is relevant\n- End with recap slide (3 bullets) and check-yourself question box (5 questions)"
    }
  ]
}
```

## Node 5 — Thumbnail Brief Generator
Type: HTTP Request → Claude API

Body:
```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 1000,
  "messages": [
    {
      "role": "user",
      "content": "You are helping design YouTube thumbnails for Rich Education, a faceless K-12 educational channel.\n\nGenerate a thumbnail design brief for:\nTopic: {{ $node['Set Variables'].json.topic }}\nGrade: {{ $node['Set Variables'].json.grade }}\nSubject: {{ $node['Set Variables'].json.subject }}\nVideo title: {{ $node['Set Variables'].json.video_title }}\n\nBrand rules:\n- Dark navy background (#1a1a2e)\n- Gold/yellow accent (#f5c518)\n- White main text, gray secondary\n- Bold blocky font\n- No real photos of people, silhouette illustrations only\n- Leave bottom-left corner for Rich Education logo badge\n- Size: 1280x720\n\nOutput:\n- Background\n- Focal visual (what, where, style)\n- Main headline text (3-5 words, which word is gold)\n- Sub-label/badge (text, color, placement)\n- Emotion trigger\n- Overall mood (1 sentence)\n- Midjourney prompt for the focal visual (flat vector, dark navy, gold/white, no faces, no text --ar 16:9 --style raw)"
    }
  ]
}
```

## Node 6 — Aggregate All Outputs
Type: Set

```json
{
  "topic": "{{ $node['Set Variables'].json.topic }}",
  "grade": "{{ $node['Set Variables'].json.grade }}",
  "subject": "{{ $node['Set Variables'].json.subject }}",
  "video_title": "{{ $node['Set Variables'].json.video_title }}",
  "script": "{{ $node['Script Generator'].json.content[0].text }}",
  "visuals": "{{ $node['Visual Shot List Generator'].json.content[0].text }}",
  "thumbnail": "{{ $node['Thumbnail Brief Generator'].json.content[0].text }}"
}
```

## Node 7 — Output Destination

### Option A — Google Docs
- Google Docs node → Create Document
- Title: `{{ $json.video_title }} - Rich Education Production Pack`
- Body: script + visuals + thumbnail brief in one doc

### Option B — Notion
- Notion node → Create Page in content database
- Map each field to a Notion property or block

### Option C — Slack/Discord
- Slack node → Post to #rich-education channel
- Send summary with script, shot list, and thumbnail brief

## Node 8 — Auto-fill Google Sheet
Type: Google Sheets node

- Operation: Append Row
- Spreadsheet: Rich Education Content Calendar
- Sheet: Video Pipeline
- Column mapping:
  ```
  Video #       → (auto-number or row count formula)
  Grade         → {{ $json.grade }}
  Subject       → {{ $json.subject }}
  Unit / Topic  → {{ $json.topic }}
  Video Title   → {{ $json.video_title }}
  Status        → Scripting
  Script Link   → {{ $json.google_doc_url }}
  Notes         → Auto-generated via n8n on {{ new Date().toLocaleDateString() }}
  ```
