# EPMS — HTML Web Version

This version replaces the Rich/TUI interface with server-rendered HTML. There is **no CSS and no JavaScript**; the UI uses standard HTML forms, links, tables, headings, and browser controls.

## Run

1. Put your Supabase URL and service-role key in `config.ini` under `[supabase]`.
2. Create a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`
4. Set a strong `APP_SECRET_KEY` environment variable for Flask sessions.
5. Start: `python app.py`
6. Open `http://127.0.0.1:5000/`.

If the database has no employees, the site presents first-time HR account setup.

## Roles and functionality

- Employee: profile, goals, goal progress, performance reviews, feedback.
- Manager: team, assign goals, team goals, create reviews, written reviews, feedback, profile.
- HR: employee list, add/edit/deactivate, password reset, all reviews, all goals, department report.

## Security note

Do not commit a Supabase `service_role`/secret key to a public repository. Rotate any secret that has already been exposed. The supplied `config.ini` is retained only to preserve the original project's configuration structure; replace its credentials before deployment.
