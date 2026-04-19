from functools import wraps

import psycopg2
from psycopg2 import sql
from flask import Flask, render_template, session, request, redirect, url_for


app = Flask(__name__)
app.secret_key = "secret"


# ================= DB HELPER =================
def get_cursor():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="forensic",
        user="postgres",
        password="Mohammed@5080",
    )
    return conn, conn.cursor()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("login"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


TABLES = {
    "user": {
        "table": "users",
        "pk": ["user_id"],
        "auto_pk": True,
        "update_template": "update_user_page.html",
        "delete_template": "remove_user.html",
    },
    "users": {
        "table": "users",
        "pk": ["user_id"],
        "auto_pk": True,
        "update_template": "update_user_page.html",
        "delete_template": "remove_user.html",
    },
    "user_phone_no": {
        "table": "user_phone_no",
        "pk": ["user_id", "phone_no"],
        "auto_pk": False,
    },
    "organization": {
        "table": "organization",
        "pk": ["organization_id"],
        "auto_pk": True,
        "update_template": "update_organization_page.html",
        "delete_template": "remove_organization.html",
    },
    "doctor": {
        "table": "doctor",
        "pk": ["doctor_id"],
        "auto_pk": True,
        "update_template": "update_doctor_page.html",
        "delete_template": "remove_doctor.html",
    },
    "doctor_phone_no": {
        "table": "doctor_phone_no",
        "pk": ["doctor_id", "phone_no"],
        "auto_pk": False,
    },
    "patient": {
        "table": "patient",
        "pk": ["patient_id"],
        "auto_pk": True,
        "update_template": "update_patient_page.html",
        "delete_template": "remove_patient.html",
    },
    "donor": {
        "table": "donor",
        "pk": ["donor_id"],
        "auto_pk": True,
        "update_template": "update_donor_page.html",
        "delete_template": "remove_donor.html",
    },
    "organ": {
        "table": "organ_available",
        "pk": ["organ_id"],
        "auto_pk": True,
    },
    "organ_available": {
        "table": "organ_available",
        "pk": ["organ_id"],
        "auto_pk": True,
    },
    "organization_phone_no": {
        "table": "organization_phone_no",
        "pk": ["organization_id", "phone_no"],
        "auto_pk": False,
    },
    "organization_head": {
        "table": "organization_head",
        "pk": ["organization_id", "employee_id"],
        "auto_pk": False,
        "update_template": "update_organization_head_page.html",
        "delete_template": "remove_organization_head.html",
    },
    "transaction": {
        "table": "transactions",
        "pk": ["transaction_id"],
        "auto_pk": True,
    },
    "transactions": {
        "table": "transactions",
        "pk": ["transaction_id"],
        "auto_pk": True,
    },
    "log": {
        "table": "log",
        "pk": [],
        "auto_pk": False,
    },
}

BOOLEAN_FIELDS = {"medical_insurance", "government_approved", "status"}


def database_error_message(error):
    if isinstance(error, psycopg2.errors.StringDataRightTruncation):
        return "One of the values is longer than the database column allows."
    if isinstance(error, psycopg2.errors.ForeignKeyViolation):
        return "A related ID does not exist. Add the referenced record first."
    if isinstance(error, psycopg2.errors.NotNullViolation):
        return "A required field is missing."
    if isinstance(error, psycopg2.errors.InvalidTextRepresentation):
        return "One of the values has the wrong format for its column."
    return str(error).splitlines()[0]


def get_config(alias):
    key = alias.lower()
    if key not in TABLES:
        raise KeyError(f"Unknown table alias: {alias}")
    return TABLES[key]


def get_columns(table):
    conn, cur = get_cursor()
    try:
        cur.execute(
            sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(table))
        )
        return [desc[0] for desc in cur.description]
    finally:
        cur.close()
        conn.close()


def normalize_form_value(column, value):
    if value == "":
        return None
    if column in BOOLEAN_FIELDS:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    return value


def get_form_value(column):
    for key, value in request.form.items():
        if key.lower() == column.lower():
            return normalize_form_value(column, value)
    return None


def fetch_all(config):
    table = config["table"]
    pk = config["pk"]
    conn, cur = get_cursor()
    try:
        if pk:
            order_by = sql.SQL(", ").join(sql.Identifier(col) for col in pk)
            cur.execute(
                sql.SQL("SELECT * FROM {} ORDER BY {}").format(
                    sql.Identifier(table), order_by
                )
            )
        else:
            cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))
        rows = cur.fetchall()
        fields = [desc[0] for desc in cur.description]
        return rows, fields
    finally:
        cur.close()
        conn.close()


def fetch_one(config, key_values):
    where_clause = sql.SQL(" AND ").join(
        sql.SQL("{} = %s").format(sql.Identifier(col)) for col in config["pk"]
    )
    conn, cur = get_cursor()
    try:
        cur.execute(
            sql.SQL("SELECT * FROM {} WHERE {}").format(
                sql.Identifier(config["table"]), where_clause
            ),
            key_values,
        )
        row = cur.fetchone()
        fields = [desc[0] for desc in cur.description]
        return row, fields
    finally:
        cur.close()
        conn.close()


def insert_row(config, columns):
    insert_columns = [
        column
        for column in columns
        if not (config["auto_pk"] and column in config["pk"])
    ]
    values = [get_form_value(column) for column in insert_columns]
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in insert_columns)
    column_sql = sql.SQL(", ").join(sql.Identifier(column) for column in insert_columns)

    conn, cur = get_cursor()
    try:
        cur.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(config["table"]), column_sql, placeholders
            ),
            values,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def update_row(config, columns):
    pk_values = [get_form_value(column) for column in config["pk"]]
    update_columns = [
        column
        for column in columns
        if column not in config["pk"] and get_form_value(column) is not None
    ]

    if not update_columns or any(value is None for value in pk_values):
        return

    assignments = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in update_columns
    )
    where_clause = sql.SQL(" AND ").join(
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in config["pk"]
    )
    values = [get_form_value(column) for column in update_columns] + pk_values

    conn, cur = get_cursor()
    try:
        cur.execute(
            sql.SQL("UPDATE {} SET {} WHERE {}").format(
                sql.Identifier(config["table"]), assignments, where_clause
            ),
            values,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def delete_row(config):
    pk_values = [get_form_value(column) for column in config["pk"]]
    if any(value is None for value in pk_values):
        return

    where_clause = sql.SQL(" AND ").join(
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in config["pk"]
    )
    conn, cur = get_cursor()
    try:
        cur.execute(
            sql.SQL("DELETE FROM {} WHERE {}").format(
                sql.Identifier(config["table"]), where_clause
            ),
            pk_values,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def render_table(config):
    rows, fields = fetch_all(config)
    return render_template("search_and_show_list.html", res=rows, fields=fields)


def render_add_page(alias, error_message=None):
    config = get_config(alias)
    fields = get_columns(config["table"])
    if config["auto_pk"]:
        fields = [field for field in fields if field not in config["pk"]]
    return render_template(
        "add_page.html",
        id=alias.lower(),
        fields=fields,
        error="True" if error_message else "False",
        error_message=error_message,
    )


def render_update_page(alias):
    config = get_config(alias)
    fields = get_columns(config["table"])
    template = config.get("update_template", "update_detail.html")
    empty_values = [""] * len(fields)
    return render_template(template, fields=fields, res=empty_values)


# ================= HOME =================
@app.route("/")
@app.route("/home")
@login_required
def home():
    return render_template("home.html", username=session.get("username"))


# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn, cur = get_cursor()
        try:
            cur.execute("SELECT * FROM public.login WHERE username = %s", (username,))
            res = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if res and res[1] == password:
            session["login"] = True
            session["username"] = username
            return redirect(url_for("home"))
        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# ================= SEARCH / VIEW =================
@app.route("/search_detail", methods=["GET", "POST"])
@login_required
def search_detail():
    return render_template("search_detail.html")


@app.route("/search_<alias>_details", methods=["POST"])
@login_required
def search_details(alias):
    return render_table(get_config(alias))


@app.route("/search_Transaction", methods=["POST"])
@login_required
def search_transaction():
    return render_table(get_config("transaction"))


@app.route("/search_log", methods=["POST"])
@login_required
def search_log():
    return render_table(get_config("log"))


@app.route("/show_users")
@login_required
def show_users():
    return render_table(get_config("user"))


@app.route("/show_update_detail", methods=["POST"])
@login_required
def show_update_detail():
    config = get_config("user")
    user_id = get_form_value("user_id")
    if user_id is None:
        return render_template("show_detail.html", not_found=True)

    row, fields = fetch_one(config, [user_id])
    if row is None:
        return render_template("show_detail.html", not_found=True)

    if "delete" in request.form:
        delete_row(config)
        return redirect(url_for("show_users"))

    if "update" in request.form:
        return render_template("update_detail.html", fields=fields, res=row)

    conn, cur = get_cursor()
    try:
        cur.execute("SELECT * FROM user_phone_no WHERE user_id = %s", (user_id,))
        phone_no = cur.fetchall()

        cur.execute("SELECT * FROM patient WHERE user_id = %s", (user_id,))
        res_pat = cur.fetchall()
        fields_pat = [desc[0] for desc in cur.description]

        cur.execute("SELECT * FROM donor WHERE user_id = %s", (user_id,))
        res_dnr = cur.fetchall()
        fields_dnr = [desc[0] for desc in cur.description]

        cur.execute(
            """
            SELECT DISTINCT t.*
            FROM transactions t
            LEFT JOIN patient p ON p.patient_id = t.patient_id
            LEFT JOIN donor d ON d.donor_id = t.donor_id
            WHERE p.user_id = %s OR d.user_id = %s
            """,
            (user_id, user_id),
        )
        res_trans = cur.fetchall()
        fields_trans = [desc[0] for desc in cur.description]
    finally:
        cur.close()
        conn.close()

    return render_template(
        "show_detail_2.html",
        fields=fields,
        res=row,
        phone_no=phone_no,
        fields_pat=fields_pat,
        res_pat=res_pat,
        fields_dnr=fields_dnr,
        res_dnr=res_dnr,
        fields_trans=fields_trans,
        res_trans=res_trans,
    )


# ================= ADD =================
@app.route("/add_<alias>_page", methods=["GET", "POST"])
@login_required
def add_page(alias):
    return render_add_page(alias)


@app.route("/add_<alias>", methods=["GET", "POST"])
@login_required
def add_row(alias):
    config = get_config(alias)
    if request.method == "POST":
        fields = get_columns(config["table"])
        try:
            insert_row(config, fields)
        except psycopg2.Error as error:
            return render_add_page(alias, database_error_message(error)), 400
        return render_table(config)
    return render_add_page(alias)


# ================= UPDATE =================
@app.route("/update_<alias>_page", methods=["GET", "POST"])
@login_required
def update_page(alias):
    return render_update_page(alias)


@app.route("/update_<alias>_details", methods=["POST"])
@login_required
def update_details_for_alias(alias):
    config = get_config(alias)
    try:
        update_row(config, get_columns(config["table"]))
    except psycopg2.Error as error:
        fields = get_columns(config["table"])
        return (
            render_template(
                config.get("update_template", "update_detail.html"),
                fields=fields,
                res=[get_form_value(field) or "" for field in fields],
                error_message=database_error_message(error),
            ),
            400,
        )
    return render_table(config)


@app.route("/update_details", methods=["POST"])
@login_required
def update_details():
    config = get_config("user")
    try:
        update_row(config, get_columns(config["table"]))
    except psycopg2.Error as error:
        fields = get_columns(config["table"])
        return (
            render_template(
                "update_detail.html",
                fields=fields,
                res=[get_form_value(field) or "" for field in fields],
                error_message=database_error_message(error),
            ),
            400,
        )
    return redirect(url_for("show_users"))


# ================= DELETE =================
@app.route("/remove_<alias>", methods=["GET", "POST"])
@login_required
def remove_page(alias):
    config = get_config(alias)
    return render_template(config["delete_template"])


@app.route("/del_<alias>", methods=["POST"])
@login_required
def delete_details(alias):
    config = get_config(alias)
    try:
        delete_row(config)
    except psycopg2.Error as error:
        return database_error_message(error), 400
    return render_table(config)


# ================= MISC =================
@app.route("/statistics", methods=["GET", "POST"])
@login_required
def statistics():
    return render_template("statistics.html")


@app.route("/contact_admin", methods=["GET", "POST"])
@login_required
def contact_admin():
    return render_template("contact_admin_page.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
