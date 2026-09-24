from datetime import datetime
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash

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


@app.route("/")
def index():
    if queries.count_employees() == 0:
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


# Employee
@app.route("/employee")
@role_required("employee")
def employee_dashboard():
    user = current_user()
    goals = queries.list_goals_for_employee(user["emp_id"])
    reviews = queries.list_reviews_for_employee(user["emp_id"])
    feedback = queries.list_feedback_for_employee(user["emp_id"])
    return render_template("employee/dashboard.html", user=user, goals=goals, reviews=reviews, feedback=feedback)


@app.route("/employee/profile")
@role_required("employee")
def employee_profile():
    user = current_user()
    manager = queries.get_employee_by_id(user["manager_id"]) if user.get("manager_id") else None
    return render_template("employee/profile.html", user=user, manager=manager)


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
    status = "completed" if progress == 100 else ("in_progress" if progress > 0 else "pending")
    queries.update_goal_progress(goal_id, progress, status)
    flash("Goal progress updated.", "success")
    return redirect(url_for("employee_goals"))


@app.route("/employee/reviews")
@role_required("employee")
def employee_reviews():
    return render_template("employee/reviews.html", user=current_user(), reviews=queries.list_reviews_for_employee(session["emp_id"]))


@app.route("/employee/feedback")
@role_required("employee")
def employee_feedback():
    return render_template("employee/feedback.html", user=current_user(), feedback=queries.list_feedback_for_employee(session["emp_id"]))


# Manager
@app.route("/manager")
@role_required("manager")
def manager_dashboard():
    user = current_user()
    team = queries.list_team_members(user["emp_id"])
    goals = queries.list_goals_for_team(user["emp_id"])
    reviews = queries.list_reviews_by_reviewer(user["emp_id"])
    return render_template("manager/dashboard.html", user=user, team=team, goals=goals, reviews=reviews)


@app.route("/manager/team")
@role_required("manager")
def manager_team():
    return render_template("manager/team.html", user=current_user(), team=queries.list_team_members(session["emp_id"]))


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
    team = queries.list_team_members(user["emp_id"])
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


@app.route("/manager/profile")
@role_required("manager")
def manager_profile():
    user = current_user()
    manager = queries.get_employee_by_id(user["manager_id"]) if user.get("manager_id") else None
    return render_template("employee/profile.html", user=user, manager=manager)


# HR
@app.route("/hr")
@role_required("hr")
def hr_dashboard():
    return render_template("hr/dashboard.html", user=current_user(), employees=queries.list_all_employees(), reviews=queries.list_all_reviews(), goals=queries.list_all_goals(), report=queries.average_rating_by_department())


@app.route("/hr/employees")
@role_required("hr")
def hr_employees():
    return render_template("hr/employees.html", user=current_user(), employees=queries.list_all_employees())


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
