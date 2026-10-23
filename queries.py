"""All data operations for the Employee Performance Management System,
built on top of the Supabase Python client (PostgREST under the hood)."""
from db import get_client


def _attach_names(rows, id_field, name_field):
    """For each row, look up employees.name for row[id_field] and store it
    under row[name_field]. Avoids relying on PostgREST embedded-join syntax
    (which gets fragile with multiple FKs to the same table)."""
    ids = {r[id_field] for r in rows if r.get(id_field) is not None}
    name_map = {}
    if ids:
        res = get_client().table("employees").select("emp_id,name").in_("emp_id", list(ids)).execute()
        name_map = {e["emp_id"]: e["name"] for e in res.data}
    for r in rows:
        r[name_field] = name_map.get(r.get(id_field))
    return rows


# ---------------------------------------------------------------- employees

def count_employees():
    try:
        res = get_client().table("employees").select("emp_id", count="exact").execute()
        return res.count or 0
    except Exception:
        return 0


def get_employee_by_email(email):
    try:
        res = get_client().table("employees").select("*").eq("email", email).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def get_employee_by_id(emp_id):
    try:
        res = get_client().table("employees").select("*").eq("emp_id", emp_id).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def create_employee(name, email, password_hash, salt, role, department,
                     designation, manager_id):
    payload = {
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "salt": salt,
        "role": role,
        "department": department,
        "designation": designation,
        "manager_id": manager_id,
    }
    res = get_client().table("employees").insert(payload).execute()
    return res.data[0] if res.data else None


def list_all_employees(active_only=True):
    q = get_client().table("employees").select("*")
    if active_only:
        q = q.eq("active", True)
    res = q.order("emp_id").execute()
    return res.data


def list_team_members(manager_id):
    res = (
        get_client()
        .table("employees")
        .select("*")
        .eq("manager_id", manager_id)
        .eq("active", True)
        .order("emp_id")
        .execute()
    )
    return res.data


def list_managers_and_hr():
    res = (
        get_client()
        .table("employees")
        .select("emp_id,name,email,role")
        .in_("role", ["manager", "hr"])
        .eq("active", True)
        .order("name")
        .execute()
    )
    return res.data


def update_employee_fields(emp_id, **fields):
    if not fields:
        return
    get_client().table("employees").update(fields).eq("emp_id", emp_id).execute()


def deactivate_employee(emp_id):
    get_client().table("employees").update({"active": False}).eq("emp_id", emp_id).execute()


def reset_password(emp_id, password_hash, salt):
    get_client().table("employees").update(
        {"password_hash": password_hash, "salt": salt}
    ).eq("emp_id", emp_id).execute()


# --------------------------------------------------------------------- goals

def create_goal(emp_id, assigned_by, title, description, target_date):
    payload = {
        "emp_id": emp_id,
        "assigned_by": assigned_by,
        "title": title,
        "description": description,
        "target_date": target_date,
    }
    res = get_client().table("goals").insert(payload).execute()
    return res.data[0] if res.data else None


def list_goals_for_employee(emp_id):
    res = (
        get_client()
        .table("goals")
        .select("*")
        .eq("emp_id", emp_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data





def list_goals_for_team(manager_id):
    team = list_team_members(manager_id)
    team_ids = [e["emp_id"] for e in team]
    if not team_ids:
        return []
    res = (
        get_client()
        .table("goals")
        .select("*")
        .in_("emp_id", team_ids)
        .order("created_at", desc=True)
        .execute()
    )
    goals = res.data
    name_map = {e["emp_id"]: e["name"] for e in team}
    for g in goals:
        g["employee_name"] = name_map.get(g["emp_id"])
    return goals


def list_all_goals():
    res = get_client().table("goals").select("*").order("created_at", desc=True).execute()
    return _attach_names(res.data, "emp_id", "employee_name")


def update_goal_progress(goal_id, progress, status):
    get_client().table("goals").update(
        {"progress": progress, "status": status}
    ).eq("goal_id", goal_id).execute()


def submit_goal_progress(goal_id, progress):
    get_client().table("goals").update(
        {"pending_progress": progress, "verification_status": "pending", "manager_feedback": None}
    ).eq("goal_id", goal_id).execute()


def review_goal_progress(goal_id, approved, feedback):
    goal = get_client().table("goals").select("pending_progress").eq("goal_id", goal_id).limit(1).execute()
    if not goal.data or goal.data[0].get("pending_progress") is None:
        return False
    fields = {
        "verification_status": "verified" if approved else "needs_revision",
        "manager_feedback": feedback or None,
    }
    if approved:
        progress = goal.data[0]["pending_progress"]
        fields.update({
            "progress": progress,
            "status": "completed" if progress == 100 else ("in_progress" if progress > 0 else "pending"),
            "pending_progress": None,
        })
    get_client().table("goals").update(fields).eq("goal_id", goal_id).execute()
    return True


# ---------------------------------------------------------- performance reviews

def create_review(emp_id, reviewer_id, review_period, rating, strengths,
                   improvements, comments):
    payload = {
        "emp_id": emp_id,
        "reviewer_id": reviewer_id,
        "review_period": review_period,
        "rating": rating,
        "strengths": strengths,
        "improvements": improvements,
        "comments": comments,
    }
    res = get_client().table("performance_reviews").insert(payload).execute()
    return res.data[0] if res.data else None


def list_reviews_for_employee(emp_id):
    res = (
        get_client()
        .table("performance_reviews")
        .select("*")
        .eq("emp_id", emp_id)
        .order("created_at", desc=True)
        .execute()
    )
    return _attach_names(res.data, "reviewer_id", "reviewer_name")


def list_reviews_by_reviewer(reviewer_id):
    res = (
        get_client()
        .table("performance_reviews")
        .select("*")
        .eq("reviewer_id", reviewer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return _attach_names(res.data, "emp_id", "employee_name")


def list_all_reviews():
    res = get_client().table("performance_reviews").select("*").order("created_at", desc=True).execute()
    reviews = res.data
    _attach_names(reviews, "emp_id", "employee_name")
    _attach_names(reviews, "reviewer_id", "reviewer_name")
    return reviews


def average_rating_by_department():
    employees = get_client().table("employees").select("emp_id,department").execute().data
    reviews = get_client().table("performance_reviews").select("emp_id,rating").execute().data

    dept_of = {e["emp_id"]: (e.get("department") or "Unassigned") for e in employees}
    ratings_by_dept = {}
    for r in reviews:
        if r.get("rating") is None:
            continue
        dept = dept_of.get(r["emp_id"], "Unassigned")
        ratings_by_dept.setdefault(dept, []).append(r["rating"])

    all_depts = sorted(set(dept_of.values())) or ["Unassigned"]
    result = []
    for dept in all_depts:
        ratings = ratings_by_dept.get(dept, [])
        avg = round(sum(ratings) / len(ratings), 2) if ratings else None
        result.append({"department": dept, "avg_rating": avg, "review_count": len(ratings)})
    return result


# ------------------------------------------------------------------- feedback

def create_feedback(emp_id, given_by, feedback_text):
    payload = {"emp_id": emp_id, "given_by": given_by, "feedback_text": feedback_text}
    res = get_client().table("feedback").insert(payload).execute()
    return res.data[0] if res.data else None


def list_feedback_for_employee(emp_id):
    res = (
        get_client()
        .table("feedback")
        .select("*")
        .eq("emp_id", emp_id)
        .order("created_at", desc=True)
        .execute()
    )
    return _attach_names(res.data, "given_by", "given_by_name")


def list_feedback_for_team(manager_id):
    team = list_team_members(manager_id)
    team_ids = [employee["emp_id"] for employee in team]
    if not team_ids:
        return []
    res = (
        get_client()
        .table("feedback")
        .select("*")
        .in_("emp_id", team_ids)
        .order("created_at", desc=True)
        .execute()
    )
    feedback = res.data
    employee_names = {employee["emp_id"]: employee["name"] for employee in team}
    for item in feedback:
        item["employee_name"] = employee_names.get(item.get("emp_id"))
    return _attach_names(feedback, "given_by", "given_by_name")


# ------------------------------------------------------------------ tasks

def create_task(emp_id, assigned_by, title, description, priority="medium", due_date=None, status="pending"):
    payload = {
        "emp_id": emp_id,
        "assigned_by": assigned_by,
        "title": title,
        "description": description,
        "priority": priority,
        "due_date": due_date,
        "status": status,
    }
    res = get_client().table("tasks").insert(payload).execute()
    return res.data[0] if res.data else None


def list_tasks_for_employee(emp_id):
    res = (
        get_client()
        .table("tasks")
        .select("*")
        .eq("emp_id", emp_id)
        .order("created_at", desc=True)
        .execute()
    )
    return _attach_names(res.data, "assigned_by", "assigned_by_name")


def list_tasks_for_team(manager_id):
    team = list_team_members(manager_id)
    team_ids = [e["emp_id"] for e in team]
    if not team_ids:
        return []
    res = (
        get_client()
        .table("tasks")
        .select("*")
        .in_("emp_id", team_ids)
        .order("created_at", desc=True)
        .execute()
    )
    tasks = res.data
    name_map = {e["emp_id"]: e["name"] for e in team}
    for task in tasks:
        task["employee_name"] = name_map.get(task.get("emp_id"))
    return _attach_names(tasks, "assigned_by", "assigned_by_name")


def list_all_tasks():
    res = get_client().table("tasks").select("*").order("created_at", desc=True).execute()
    tasks = res.data
    _attach_names(tasks, "emp_id", "employee_name")
    _attach_names(tasks, "assigned_by", "assigned_by_name")
    return tasks


def update_task_status(task_id, emp_id, status):
    return (
        get_client()
        .table("tasks")
        .update({"status": status})
        .eq("task_id", task_id)
        .eq("emp_id", emp_id)
        .execute()
    )


# ------------------------------------------------------------ performance scores

def create_performance_score(emp_id, education_score, work_score, misc_score, notes=None):
    total_score = round((education_score + work_score + misc_score) / 3, 2)
    payload = {
        "emp_id": emp_id,
        "education_score": education_score,
        "work_score": work_score,
        "misc_score": misc_score,
        "total_score": total_score,
        "notes": notes,
    }
    res = get_client().table("employee_performance_scores").insert(payload).execute()
    return res.data[0] if res.data else None


def get_latest_performance_score(emp_id):
    res = (
        get_client()
        .table("employee_performance_scores")
        .select("*")
        .eq("emp_id", emp_id)
        .order("assessed_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_employee_metrics(emp_id):
    user = get_employee_by_id(emp_id) or {}
    goals = list_goals_for_employee(emp_id)
    tasks = list_tasks_for_employee(emp_id)
    reviews = list_reviews_for_employee(emp_id)
    feedback = list_feedback_for_employee(emp_id)
    completed_tasks = sum(1 for t in tasks if (t.get("status") or "").lower() == "completed")
    pending_tasks = sum(1 for t in tasks if (t.get("status") or "").lower() in {"pending", "not_started"})
    in_progress_tasks = sum(1 for t in tasks if (t.get("status") or "").lower() == "in_progress")
    overdue_tasks = sum(
        1
        for t in tasks
        if (t.get("status") or "").lower() not in {"completed", "closed"} and t.get("due_date") and t["due_date"] < __import__("datetime").date.today().isoformat()
    )
    score = get_latest_performance_score(emp_id)
    if not score:
        score = {
            "education_score": min(100, 75 + len(goals) * 3),
            "work_score": min(100, 70 + len(tasks) * 4),
            "misc_score": min(100, 60 + len(feedback) * 5),
            "total_score": 0,
        }
        score["total_score"] = round((score["education_score"] + score["work_score"] + score["misc_score"]) / 3, 2)

    work_completion = 0
    if tasks:
        work_completion = round((completed_tasks / len(tasks)) * 100, 2)

    metrics = {
        "goals": goals,
        "tasks": tasks,
        "reviews": reviews,
        "feedback": feedback,
        "score": score,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "overdue_tasks": overdue_tasks,
        "total_tasks": len(tasks),
        "work_completion": work_completion,
        "training_hours": user.get("training_hours") or 0,
        "years_experience": user.get("years_experience") or 0,
        "skills": user.get("skills") or "",
        "department": user.get("department") or "Unassigned",
        "designation": user.get("designation") or "",
    }
    return metrics


def get_task_recommendations(emp_id):
    user = get_employee_by_id(emp_id) or {}
    dept = (user.get("department") or "General").lower()
    role = (user.get("role") or "employee").lower()
    years = user.get("years_experience") or 0
    recs = [
        "Documentation update",
        "Weekly report preparation",
        "Client follow-up and coordination",
        "Process improvement review",
        "Training session support",
    ]
    if dept in {"engineering", "it", "technology"}:
        recs = ["Code review", "Bug triage", "Feature testing", "Automation task", "Technical documentation"]
    elif dept in {"sales", "marketing"}:
        recs = ["Lead qualification", "Campaign analysis", "Client presentation", "Market research", "Sales follow-up"]
    elif dept in {"hr", "human resources"}:
        recs = ["Onboarding checklist", "Policy review", "Employee engagement survey", "Training coordination", "Recruitment support"]
    if years >= 5:
        recs.insert(0, "Mentorship and knowledge transfer")
    if role == "manager":
        recs.insert(0, "Team planning review")
    return recs[:6]


# ------------------------------------------------------------------------- appeals

def create_appeal(emp_id, raised_by, authority, subject, description, priority="normal", proof_path=None):
    payload = {
        "emp_id": emp_id,
        "raised_by": raised_by,
        "authority": authority,
        "subject": subject,
        "description": description,
        "priority": priority,
        "status": "open",
        "proof_path": proof_path,
    }
    res = get_client().table("appeals").insert(payload).execute()
    return res.data[0] if res.data else None


def add_appeal_update(appeal_id, commenter_id, comment, response=None, status=None):
    payload = {
        "appeal_id": appeal_id,
        "commenter_id": commenter_id,
        "comment": comment,
        "response": response,
        "status": status or "reviewed",
    }
    res = get_client().table("appeal_updates").insert(payload).execute()
    return res.data[0] if res.data else None


def list_appeals_for_employee(emp_id):
    res = (
        get_client()
        .table("appeals")
        .select("*")
        .eq("emp_id", emp_id)
        .order("created_at", desc=True)
        .execute()
    )
    appeals = _attach_names(res.data, "raised_by", "raised_by_name")
    return _attach_appeal_proof_urls(appeals)


def list_appeals_for_manager(manager_id):
    team = list_team_members(manager_id)
    team_ids = [e["emp_id"] for e in team]
    if not team_ids:
        return []
    res = (
        get_client()
        .table("appeals")
        .select("*")
        .in_("emp_id", team_ids)
        .order("created_at", desc=True)
        .execute()
    )
    appeals = res.data
    _attach_names(appeals, "emp_id", "employee_name")
    _attach_names(appeals, "raised_by", "raised_by_name")
    return _attach_appeal_proof_urls(appeals)


def list_all_appeals():
    res = get_client().table("appeals").select("*").order("created_at", desc=True).execute()
    appeals = res.data
    _attach_names(appeals, "emp_id", "employee_name")
    _attach_names(appeals, "raised_by", "raised_by_name")
    return _attach_appeal_proof_urls(appeals)


def _attach_appeal_proof_urls(appeals):
    for appeal in appeals:
        path = appeal.get("proof_path")
        if path:
            try:
                result = get_client().storage.from_("appeal-proofs").create_signed_url(path, 3600)
                appeal["proof_url"] = result.get("signedURL") or result.get("signedUrl")
            except Exception:
                appeal["proof_url"] = None
    return appeals


def list_appeal_updates(appeal_id):
    res = (
        get_client()
        .table("appeal_updates")
        .select("*")
        .eq("appeal_id", appeal_id)
        .order("created_at", asc=True)
        .execute()
    )
    updates = res.data
    _attach_names(updates, "commenter_id", "commenter_name")
    return updates


def update_appeal_status(appeal_id, status):
    get_client().table("appeals").update({"status": status}).eq("appeal_id", appeal_id).execute()
