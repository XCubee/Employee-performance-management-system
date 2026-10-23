from datetime import datetime
import os
import re
import uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.exceptions import HTTPException

import auth
import queries

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY", "change-this-secret-key")


def current_user():
    emp_id = session.get("emp_id")
    return queries.get_employee_by_id(emp_id) if emp_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("emp_id"):
            return redirect(url_for("login"))
        user = current_user()
        if not user or not user.get("active"):
            session.clear()
            flash("Your account is inactive or no longer available.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles:
                flash("You do not have permission to access that page.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    error_name = type(error).__name__
    message = str(error)
    if ("ConnectError" in error_name or "Timeout" in error_name or "getaddrinfo failed" in message):
        flash("The database is currently unavailable. Please check the Supabase URL and key in config.ini.", "error")
        return redirect(url_for("login"))
    raise error


@app.route("/")
def index():
    try:
        employee_count = queries.count_employees()
    except Exception:
        employee_count = 0
    if employee_count == 0:
        return redirect(url_for("setup"))
    if session.get("emp_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if queries.count_employees() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not name or not email or not password:
            flash("Name, email, and password are required.", "error")
        else:
            password_hash, salt = auth.hash_password(password)
            queries.create_employee(name, email, password_hash, salt, "hr", "Human Resources", "HR Administrator", None)
            flash("HR account created. You can now log in.", "success")
            return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = auth.login(request.form.get("email", "").strip(), request.form.get("password", ""))
        if user:
            session.clear()
            session["emp_id"] = user["emp_id"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid credentials or inactive account.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    if role == "hr":
        return redirect(url_for("hr_dashboard"))
    if role == "manager":
        return redirect(url_for("manager_dashboard"))
    return redirect(url_for("employee_dashboard"))


@app.route("/employee")
@role_required("employee")
def employee_dashboard():
    user = current_user()
    goals = queries.list_goals_for_employee(user["emp_id"])
    tasks = queries.list_tasks_for_employee(user["emp_id"])
    reviews = queries.list_reviews_for_employee(user["emp_id"])
    feedback = queries.list_feedback_for_employee(user["emp_id"])
    return render_template("employee/dashboard.html", user=user, goals=goals, tasks=tasks, reviews=reviews, feedback=feedback)


@app.route("/employee/profile")
@role_required("employee")
def employee_profile():
    user = current_user()
    manager = queries.get_employee_by_id(user["manager_id"]) if user.get("manager_id") else None
    feedback = queries.list_feedback_for_employee(user["emp_id"])
    return render_template("employee/profile.html", user=user, manager=manager, feedback=feedback)


@app.route("/employee/goals")
@role_required("employee")
def employee_goals():
    return render_template("employee/goals.html", user=current_user(), goals=queries.list_goals_for_employee(session["emp_id"]))


@app.route("/employee/goals/<int:goal_id>/progress", methods=["POST"])
@role_required("employee")
def employee_goal_progress(goal_id):
    goals = queries.list_goals_for_employee(session["emp_id"])
    if not any(g["goal_id"] == goal_id for g in goals):
        flash("Invalid goal ID.", "error")
        return redirect(url_for("employee_goals"))
    try:
        progress = max(0, min(100, int(request.form.get("progress", "0"))))
    except ValueError:
        flash("Progress must be a number from 0 to 100.", "error")
        return redirect(url_for("employee_goals"))
    queries.submit_goal_progress(goal_id, progress)
    flash("Progress submitted for manager verification.", "success")
    return redirect(url_for("employee_goals"))


@app.route("/employee/tasks/<int:task_id>/status", methods=["POST"])
@role_required("employee")
def employee_task_status(task_id):
    emp_id = session["emp_id"]
    task = next((task for task in queries.list_tasks_for_employee(emp_id) if task["task_id"] == task_id), None)
    status = request.form.get("status", "")
    if not task:
        flash("Task not found for your account.", "error")
    elif status not in {"pending", "not_started", "in_progress", "completed"}:
        flash("Choose a valid task status.", "error")
    else:
        queries.update_task_status(task_id, emp_id, status)
        flash("Task status updated.", "success")
    return redirect(request.referrer or url_for("employee_dashboard"))


@app.route("/employee/reviews")
@role_required("employee")
def employee_reviews():
    return render_template("employee/reviews.html", user=current_user(), reviews=queries.list_reviews_for_employee(session["emp_id"]))


@app.route("/employee/feedback")
@role_required("employee")
def employee_feedback():
    return render_template("employee/feedback.html", user=current_user(), feedback=queries.list_feedback_for_employee(session["emp_id"]))


@app.route("/employee/metrics")
@role_required("employee")
def employee_metrics():
    user = current_user()
    metrics = queries.get_employee_metrics(user["emp_id"])
    return render_template("employee/metrics.html", user=user, metrics=metrics)


@app.route("/employee/appeals", methods=["GET", "POST"])
@role_required("employee")
def employee_appeals():
    user = current_user()
    if request.method == "POST":
        authority = request.form.get("authority", "HR").strip() or "HR"
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "normal").strip() or "normal"
        if not subject or not description:
            flash("Subject and description are required.", "error")
        else:
            proof_path = upload_appeal_proof(request.files.get("proof"), user["emp_id"])
            if request.files.get("proof") and not proof_path:
                return redirect(url_for("employee_appeals"))
            queries.create_appeal(user["emp_id"], user["emp_id"], authority, subject, description, priority, proof_path)
            flash("Appeal raised successfully.", "success")
            return redirect(url_for("employee_appeals"))
    appeals = queries.list_appeals_for_employee(user["emp_id"])
    return render_template("employee/appeals.html", user=user, appeals=appeals)


@app.route("/manager")
@role_required("manager")
def manager_dashboard():
    user = current_user()
    team = queries.list_team_members(user["emp_id"])
    goals = queries.list_goals_for_team(user["emp_id"])
    reviews = queries.list_reviews_by_reviewer(user["emp_id"])
    tasks = queries.list_tasks_for_team(user["emp_id"])
    return render_template("manager/dashboard.html", user=user, team=team, goals=goals, reviews=reviews, tasks=tasks)


@app.route("/manager/team")
@role_required("manager")
def manager_team():
    team = queries.list_team_members(session["emp_id"])
    team = add_team_activity(
        team,
        queries.list_tasks_for_team(session["emp_id"]),
        queries.list_feedback_for_team(session["emp_id"]),
    )
    return render_template("manager/team.html", user=current_user(), team=team)


def add_team_activity(team, tasks, feedback):
    tasks_by_employee = {}
    for task in tasks:
        tasks_by_employee.setdefault(task.get("emp_id"), []).append(task)

    feedback_by_employee = {}
    for item in feedback:
        feedback_by_employee.setdefault(item.get("emp_id"), []).append(item)

    profiles = []
    for employee in team:
        profile = dict(employee)
        employee_tasks = tasks_by_employee.get(employee["emp_id"], [])
        completed_tasks = sum(
            1 for task in employee_tasks
            if (task.get("status") or "").lower() == "completed"
        )
        profile["tasks"] = employee_tasks
        profile["work_completion"] = (
            round((completed_tasks / len(employee_tasks)) * 100, 2)
            if employee_tasks else 0
        )
        profile["feedback"] = feedback_by_employee.get(employee["emp_id"], [])
        profiles.append(profile)
    return profiles


def team_member_or_none(emp_id):
    team = queries.list_team_members(session["emp_id"])
    try:
        emp_id = int(emp_id)
    except (ValueError, TypeError):
        return None
    return next((e for e in team if e["emp_id"] == emp_id), None)


@app.route("/manager/goals", methods=["GET", "POST"])
@role_required("manager")
def manager_goals():
    user = current_user()
    team = queries.list_team_members(user["emp_id"])
    if request.method == "POST":
        emp = team_member_or_none(request.form.get("emp_id"))
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        target_date = request.form.get("target_date", "").strip() or None
        if not emp or not title:
            flash("A valid team member and goal title are required.", "error")
        else:
            if target_date:
                try:
                    datetime.strptime(target_date, "%Y-%m-%d")
                except ValueError:
                    flash("Invalid target date.", "error")
                    return render_template("manager/goals.html", user=user, team=team, goals=queries.list_goals_for_team(user["emp_id"]))
            queries.create_goal(emp["emp_id"], user["emp_id"], title, description, target_date)
            flash("Goal assigned.", "success")
            return redirect(url_for("manager_goals"))
    return render_template("manager/goals.html", user=user, team=team, goals=queries.list_goals_for_team(user["emp_id"]))


@app.route("/manager/goals/<int:goal_id>/verify", methods=["POST"])
@role_required("manager")
def manager_verify_goal(goal_id):
    user = current_user()
    goal = next((g for g in queries.list_goals_for_team(user["emp_id"]) if g["goal_id"] == goal_id), None)
    if not goal:
        flash("Goal not found for your team.", "error")
        return redirect(url_for("manager_goals"))
    action = request.form.get("action")
    if goal.get("verification_status") != "pending" or action not in {"verify", "revise"}:
        flash("This goal has no pending progress update to review.", "error")
    else:
        reviewed = queries.review_goal_progress(
            goal_id,
            action == "verify",
            request.form.get("manager_feedback", "").strip(),
        )
        flash("Progress verified." if action == "verify" else "Revision requested.", "success" if reviewed else "error")
    return redirect(url_for("manager_goals"))


@app.route("/manager/reviews", methods=["GET", "POST"])
@role_required("manager")
def manager_reviews():
    user = current_user()
    team = queries.list_team_members(user["emp_id"])
    if request.method == "POST":
        emp = team_member_or_none(request.form.get("emp_id"))
        period = request.form.get("review_period", "").strip()
        rating = request.form.get("rating", "")
        if not emp or not period or rating not in {"1", "2", "3", "4", "5"}:
            flash("Team member, review period, and rating are required.", "error")
        else:
            queries.create_review(emp["emp_id"], user["emp_id"], period, int(rating), request.form.get("strengths", "").strip(), request.form.get("improvements", "").strip(), request.form.get("comments", "").strip())
            flash("Review submitted.", "success")
            return redirect(url_for("manager_reviews"))
    return render_template("manager/reviews.html", user=user, team=team, reviews=queries.list_reviews_by_reviewer(user["emp_id"]))


@app.route("/manager/feedback", methods=["GET", "POST"])
@role_required("manager")
def manager_feedback():
    user = current_user()
    team = add_team_activity(
        queries.list_team_members(user["emp_id"]),
        queries.list_tasks_for_team(user["emp_id"]),
        [],
    )
    if request.method == "POST":
        emp = team_member_or_none(request.form.get("emp_id"))
        text = request.form.get("feedback_text", "").strip()
        if not emp or not text:
            flash("Team member and feedback message are required.", "error")
        else:
            queries.create_feedback(emp["emp_id"], user["emp_id"], text)
            flash("Feedback recorded.", "success")
            return redirect(url_for("manager_feedback"))
    return render_template("manager/feedback.html", user=user, team=team)


@app.route("/manager/tasks", methods=["GET", "POST"])
@role_required("manager")
def manager_tasks():
    user = current_user()
    team = queries.list_team_members(user["emp_id"])
    title = request.form.get("title", "").strip() if request.method == "POST" else ""
    description = request.form.get("description", "").strip() if request.method == "POST" else ""
    task_list = queries.list_tasks_for_team(user["emp_id"])
    team_profiles = add_team_activity(
        team,
        task_list,
        queries.list_feedback_for_team(user["emp_id"]),
    )
    candidates = score_task_candidates(team, task_list, title, description)
    profiles_by_employee = {profile["emp_id"]: profile for profile in team_profiles}
    for candidate in candidates:
        profile = profiles_by_employee[candidate["emp_id"]]
        candidate["work_completion"] = profile["work_completion"]
        candidate["feedback"] = profile["feedback"]
        candidate["tasks"] = profile["tasks"]
    selected_emp_id = request.form.get("emp_id", type=int) if request.method == "POST" else None
    if selected_emp_id not in {candidate["emp_id"] for candidate in candidates}:
        selected_emp_id = candidates[0]["emp_id"] if candidates else None
    selected_candidate = next(
        (candidate for candidate in candidates if candidate["emp_id"] == selected_emp_id),
        None,
    )
    if request.method == "POST":
        priority = request.form.get("priority", "medium").strip() or "medium"
        due_date = request.form.get("due_date", "").strip() or None
        if request.form.get("action") == "assign":
            emp = team_member_or_none(selected_emp_id)
            if not emp or not title:
                flash("Choose a candidate and enter a task title.", "error")
            else:
                queries.create_task(emp["emp_id"], user["emp_id"], title, description, priority, due_date)
                flash("Task assigned to the selected candidate.", "success")
                return redirect(url_for("manager_tasks"))

    return render_template(
        "manager/tasks.html",
        user=user,
        team=team,
        tasks=task_list,
        candidates=candidates,
        selected_emp_id=selected_emp_id,
        selected_candidate=selected_candidate,
        title=title,
        description=description,
    )


def score_task_candidates(team, tasks, title, description):
    stop_words = {"about", "after", "also", "and", "for", "from", "into", "that", "the", "this", "with", "your"}
    requested = {word for word in re.findall(r"[a-z0-9]+", f"{title} {description}".lower()) if len(word) > 2 and word not in stop_words}
    candidates = []
    for employee in team:
        active_tasks = [
            task for task in tasks
            if task.get("emp_id") == employee["emp_id"]
            and (task.get("status") or "").lower() not in {"completed", "closed"}
        ]
        skill_words = {word for word in re.findall(r"[a-z0-9]+", (employee.get("skills") or "").lower()) if len(word) > 2}
        skill_match = len(requested & skill_words) / len(requested) if requested else 0.5
        workload = min(len(active_tasks), 6)
        score = round(skill_match * 70 + (1 - workload / 6) * 30)
        employee_candidate = dict(employee)
        employee_candidate.update({
            "fit_score": score,
            "active_tasks": len(active_tasks),
            "current_projects": [task["title"] for task in active_tasks],
            "active_task_details": active_tasks,
        })
        candidates.append(employee_candidate)
    return sorted(candidates, key=lambda candidate: (-candidate["fit_score"], candidate["name"].lower()))


@app.route("/manager/appeals", methods=["GET", "POST"])
@role_required("manager")
def manager_appeals():
    user = current_user()
    team = queries.list_team_members(user["emp_id"])
    if request.method == "POST":
        emp = team_member_or_none(request.form.get("emp_id"))
        authority = request.form.get("authority", "HR").strip() or "HR"
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        if not emp or not subject or not description:
            flash("Employee, subject, and description are required.", "error")
        else:
            proof_path = upload_appeal_proof(request.files.get("proof"), emp["emp_id"])
            if request.files.get("proof") and not proof_path:
                return redirect(url_for("manager_appeals"))
            queries.create_appeal(emp["emp_id"], user["emp_id"], authority, subject, description, "high", proof_path)
            flash("Appeal escalated successfully.", "success")
            return redirect(url_for("manager_appeals"))
    appeals = queries.list_appeals_for_manager(user["emp_id"])
    return render_template("manager/appeals.html", user=user, team=team, appeals=appeals)


def upload_appeal_proof(upload, emp_id):
    if not upload or not upload.filename:
        return None
    extension = os.path.splitext(upload.filename)[1].lower()
    content_type = upload.mimetype or ""
    allowed = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    if extension not in allowed or content_type not in set(allowed.values()):
        flash("Proof must be a JPG, PNG, or WebP image.", "error")
        return None
    contents = upload.read(5 * 1024 * 1024 + 1)
    if not contents or len(contents) > 5 * 1024 * 1024:
        flash("Proof image must be smaller than 5 MB.", "error")
        return None
    path = f"{emp_id}/{uuid.uuid4().hex}{extension}"
    try:
        queries.get_client().storage.from_("appeal-proofs").upload(
            path, contents, {"content-type": content_type}
        )
    except Exception:
        flash("Could not upload proof image. Check the Supabase bucket setup and server key.", "error")
        return None
    return path


@app.route("/manager/profile")
@role_required("manager")
def manager_profile():
    user = current_user()
    manager = queries.get_employee_by_id(user["manager_id"]) if user.get("manager_id") else None
    feedback = queries.list_feedback_for_employee(user["emp_id"])
    return render_template("employee/profile.html", user=user, manager=manager, feedback=feedback)


@app.route("/hr")
@role_required("hr")
def hr_dashboard():
    return render_template("hr/dashboard.html", user=current_user(), employees=queries.list_all_employees(), reviews=queries.list_all_reviews(), goals=queries.list_all_goals(), report=queries.average_rating_by_department())


@app.route("/hr/employees")
@role_required("hr")
def hr_employees():
    return render_template("hr/employees.html", user=current_user(), employees=queries.list_all_employees())


@app.route("/hr/hierarchy")
@role_required("hr")
def hr_hierarchy():
    employees = queries.list_all_employees()
    nodes = {
        employee["emp_id"]: {"employee": employee, "reports": []}
        for employee in employees
    }
    roots = []

    for employee in employees:
        node = nodes[employee["emp_id"]]
        manager_id = employee.get("manager_id")
        if manager_id in nodes and manager_id != employee["emp_id"]:
            nodes[manager_id]["reports"].append(node)
        else:
            roots.append(node)

    for node in nodes.values():
        node["reports"].sort(
            key=lambda report: (report["employee"].get("name") or "").casefold()
        )

    included = set()

    def build_tree(node, ancestors):
        employee = node["employee"]
        emp_id = employee["emp_id"]
        if emp_id in ancestors or emp_id in included:
            return None

        included.add(emp_id)
        next_ancestors = ancestors | {emp_id}
        return {
            "employee": employee,
            "reports": [
                tree
                for report in node["reports"]
                if (tree := build_tree(report, next_ancestors)) is not None
            ],
        }

    hierarchy = [
        tree
        for root in roots
        if (tree := build_tree(root, set())) is not None
    ]
    for employee in sorted(
        employees, key=lambda item: (item.get("name") or "").casefold()
    ):
        node = nodes[employee["emp_id"]]
        if employee["emp_id"] not in included:
            tree = build_tree(node, set())
            if tree is not None:
                hierarchy.append(tree)

    return render_template("hr/hierarchy.html", user=current_user(), hierarchy=hierarchy)


@app.route("/hr/employees/add", methods=["GET", "POST"])
@role_required("hr")
def hr_add_employee():
    managers = queries.list_managers_and_hr()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "employee")
        department = request.form.get("department", "").strip()
        designation = request.form.get("designation", "").strip()
        if not name or not email or not password or role not in {"hr", "manager", "employee"}:
            flash("Name, email, password, and a valid role are required.", "error")
        elif queries.get_employee_by_email(email):
            flash("An employee with that email already exists.", "error")
        else:
            manager_id = request.form.get("manager_id") or None
            if manager_id:
                try:
                    manager_id = int(manager_id)
                    if not any(m["emp_id"] == manager_id for m in managers):
                        manager_id = None
                except ValueError:
                    manager_id = None
            if role == "hr":
                manager_id = None
            password_hash, salt = auth.hash_password(password)
            queries.create_employee(name, email, password_hash, salt, role, department, designation, manager_id)
            flash(f"Employee '{name}' created.", "success")
            return redirect(url_for("hr_employees"))
    return render_template("hr/add_employee.html", user=current_user(), managers=managers)


@app.route("/hr/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@role_required("hr")
def hr_edit_employee(emp_id):
    emp = queries.get_employee_by_id(emp_id)
    if not emp:
        flash("Employee not found.", "error")
        return redirect(url_for("hr_employees"))
    if request.method == "POST":
        updates = {}
        for field in ("name", "department", "designation", "role"):
            value = request.form.get(field, "").strip()
            if field == "role" and value not in {"hr", "manager", "employee"}:
                continue
            if value != (emp.get(field) or ""):
                updates[field] = value
        if updates:
            queries.update_employee_fields(emp_id, **updates)
            flash("Employee updated.", "success")
        else:
            flash("No changes made.", "info")
        return redirect(url_for("hr_employees"))
    return render_template("hr/edit_employee.html", user=current_user(), employee=emp)


@app.route("/hr/employees/<int:emp_id>/deactivate", methods=["POST"])
@role_required("hr")
def hr_deactivate_employee(emp_id):
    emp = queries.get_employee_by_id(emp_id)
    if not emp:
        flash("Employee not found.", "error")
    elif emp_id == session["emp_id"]:
        flash("You cannot deactivate your own account.", "error")
    else:
        queries.deactivate_employee(emp_id)
        flash("Employee deactivated.", "success")
    return redirect(url_for("hr_employees"))


@app.route("/hr/employees/<int:emp_id>/password", methods=["GET", "POST"])
@role_required("hr")
def hr_reset_password(emp_id):
    emp = queries.get_employee_by_id(emp_id)
    if not emp:
        flash("Employee not found.", "error")
        return redirect(url_for("hr_employees"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if not password:
            flash("Password cannot be empty.", "error")
        else:
            password_hash, salt = auth.hash_password(password)
            queries.reset_password(emp_id, password_hash, salt)
            flash("Password reset.", "success")
            return redirect(url_for("hr_employees"))
    return render_template("hr/reset_password.html", user=current_user(), employee=emp)


@app.route("/hr/reviews")
@role_required("hr")
def hr_reviews():
    return render_template("hr/reviews.html", user=current_user(), reviews=queries.list_all_reviews())


@app.route("/hr/goals")
@role_required("hr")
def hr_goals():
    return render_template("hr/goals.html", user=current_user(), goals=queries.list_all_goals())


@app.route("/hr/report")
@role_required("hr")
def hr_report():
    return render_template("hr/report.html", user=current_user(), report=queries.average_rating_by_department())


@app.route("/hr/appeals")
@role_required("hr")
def hr_appeals():
    appeals = queries.list_all_appeals()
    return render_template("hr/appeals.html", user=current_user(), appeals=appeals)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
