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
    res = get_client().table("employees").select("emp_id", count="exact").execute()
    return res.count or 0


def get_employee_by_email(email):
    res = get_client().table("employees").select("*").eq("email", email).limit(1).execute()
    return res.data[0] if res.data else None


def get_employee_by_id(emp_id):
    res = get_client().table("employees").select("*").eq("emp_id", emp_id).limit(1).execute()
    return res.data[0] if res.data else None


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
