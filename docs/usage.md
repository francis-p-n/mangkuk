# Running it

Python 3.12.

```bash
pip install -r requirements/base.txt
```

The dependency list is under `requirements/` rather than at the repository
root, and that location is deliberate. Vercel decides a project is a Python
application when it finds `requirements.txt`, `pyproject.toml` or `Pipfile` at
the root, and then looks for `app.py`, `index.py`, `server.py`, `main.py`,
`wsgi.py` or `asgi.py` to serve. There is no such file here - the web app is a
Next.js project in `web/` - so the build failed on a repository that contains
no Python web server at all, and offered to deploy the `Handler` class out of
a test instead. That detection happens before any configuration is read, so
nothing in `vercel.json` can prevent it. Moving one file does.

## The check itself

```bash
python run.py
```

Reads `data/`, writes `out/submission.json` (the scored file) and
`out/results.json` (everything a human needs).

| Command | What it does |
|---|---|
| `python -m pytest tests -q` | the test suite |
| `python eval/rubric.py` | check every claim in [validation](validation.md) against a live run |
| `python eval/rubric.py --loop` | the same, re-running until they all pass |
| `python eval/mutation.py` | inject defects, measure detection |
| `python eval/desk_cases.py` | real-world document quirks |
| `python eval/audit.py` | audit a run with no ground truth |
| `python eval/score.py --truth gt.json` | score against the organizers' truth |
| `python run.py --source http://host:8080` | run against their server |
| `python run.py --agent gemini` | turn the LLM recovery stage on |
| `python run.py --learned overrides.json` | apply the desk's own corrections |
| `python tools/demo_data.py` | scramble the data for public sharing |

Agent providers: `bedrock` (keeps document text inside the tenant),
`anthropic`, `gemini`. Default is `off`, so the scored run stays
deterministic and needs no key.

## The website

```bash
python tools/supabase_load.py     # load a run into Supabase
npm run dev --prefix web          # the Next.js app against it
```

Needs `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` to load, and
`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` to read. Copy
`.env.example` and fill it in. Apply `supabase/migrations/0001_results.sql`
first, or there are no tables to write to.

The loader defaults to the scrambled build and refuses the real one without
`--real`: the anon key the site ships with can read the whole table.

## Deploying

Vercel's **Root Directory** setting picks what deploys.

| Root Directory | What deploys |
|---|---|
| `web` | the Next.js app, reading the run out of Supabase |
| `out/site-demo` | the static build, with the data inlined |

Leave it at the repository root and nothing sensible happens - there is no
application there, only the pipeline that feeds one.
