from functools import wraps
from datetime import date

import psycopg2
from psycopg2 import sql
from flask import Flask, flash, render_template, session, request, redirect, url_for


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
        "display": "User",
        "unique_fields": ["name", "date_of_birth"],
    },
    "users": {
        "table": "users",
        "pk": ["user_id"],
        "auto_pk": True,
        "display": "User",
        "unique_fields": ["name", "date_of_birth"],
    },
    "user_phone_no": {
        "table": "user_phone_no",
        "pk": ["user_id", "phone_no"],
        "auto_pk": False,
        "display": "User Phone Number",
    },
    "organization": {
        "table": "organization",
        "pk": ["organization_id"],
        "auto_pk": True,
        "display": "Organization",
    },
    "doctor": {
        "table": "doctor",
        "pk": ["doctor_id"],
        "auto_pk": True,
        "display": "Doctor",
    },
    "doctor_phone_no": {
        "table": "doctor_phone_no",
        "pk": ["doctor_id", "phone_no"],
        "auto_pk": False,
        "display": "Doctor Phone Number",
    },
    "patient": {
        "table": "patient",
        "pk": ["patient_id"],
        "auto_pk": True,
        "display": "Patient",
    },
    "donor": {
        "table": "donor",
        "pk": ["donor_id"],
        "auto_pk": True,
        "display": "Donor",
    },
    "organ": {
        "table": "organ_available",
        "pk": ["organ_id"],
        "auto_pk": True,
        "display": "Organ",
    },
    "organ_available": {
        "table": "organ_available",
        "pk": ["organ_id"],
        "auto_pk": True,
        "display": "Organ",
    },
    "organization_phone_no": {
        "table": "organization_phone_no",
        "pk": ["organization_id", "phone_no"],
        "auto_pk": False,
        "display": "Organization Phone Number",
    },
    "organization_head": {
        "table": "organization_head",
        "pk": ["organization_id", "employee_id"],
        "auto_pk": False,
        "display": "Organization Head",
    },
    "transaction": {
        "table": "transactions",
        "pk": ["transaction_id"],
        "auto_pk": True,
        "display": "Transaction",
    },
    "transactions": {
        "table": "transactions",
        "pk": ["transaction_id"],
        "auto_pk": True,
        "display": "Transaction",
    },
    "log": {
        "table": "log",
        "pk": [],
        "auto_pk": False,
        "display": "Log",
    },
}

BOOLEAN_FIELDS = {"medical_insurance", "government_approved", "status"}
INTEGER_TYPES = {"smallint", "integer", "bigint"}
DATE_TYPES = {"date"}


def database_error_message(error):
    if isinstance(error, psycopg2.errors.StringDataRightTruncation):
        return "One of the values is longer than the database column allows."
    if isinstance(error, psycopg2.errors.UniqueViolation):
        return "A record with these unique details already exists."
    if isinstance(error, psycopg2.errors.ForeignKeyViolation):
        return "A related ID does not exist. Add the referenced record first."
    if isinstance(error, psycopg2.errors.NotNullViolation):
        return "A required field is missing."
    if isinstance(error, psycopg2.errors.InvalidTextRepresentation):
        return "One of the values has the wrong format for its column."
    return str(error).splitlines()[0]


def field_label(field):
    return field.replace("_", " ").title()


def field_input_type(field):
    if field in BOOLEAN_FIELDS:
        return "checkbox"
    if field.endswith("_id") or field in {"employee_id", "term_length"}:
        return "number"
    if "date" in field:
        return "date"
    return "text"


@app.context_processor
def template_helpers():
    return {
        "boolean_fields": BOOLEAN_FIELDS,
        "field_input_type": field_input_type,
        "field_label": field_label,
    }


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


def get_column_info(table):
    conn, cur = get_cursor()
    try:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return {
            name: {
                "data_type": data_type,
                "nullable": nullable == "YES",
                "max_length": max_length,
            }
            for name, data_type, nullable, max_length in cur.fetchall()
        }
    finally:
        cur.close()
        conn.close()


def get_raw_form_value(column):
    for key in request.form.keys():
        if key.lower() == column.lower():
            values = request.form.getlist(key)
            if not values:
                return None
            return values[-1].strip()
    return None


def normalize_form_value(column, value):
    if value == "":
        return None
    if column in BOOLEAN_FIELDS:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    return value


def get_form_value(column):
    value = get_raw_form_value(column)
    if value is None:
        return None
    return normalize_form_value(column, value)


def validate_boolean(column, raw_value):
    if raw_value is None or raw_value == "":
        return True
    return raw_value.lower() in {"1", "0", "true", "false", "yes", "no", "on", "off"}


def validate_form(config, columns, mode):
    metadata = get_column_info(config["table"])
    errors = []

    for column in columns:
        if mode == "insert" and config["auto_pk"] and column in config["pk"]:
            continue

        raw_value = get_raw_form_value(column)
        value = get_form_value(column)
        info = metadata.get(column, {})
        label = field_label(column)
        is_required = not info.get("nullable", True)

        if mode == "update" and column in config["pk"]:
            is_required = True

        if is_required and value is None:
            errors.append(f"{label} is required.")
            continue

        if value is None:
            continue

        data_type = info.get("data_type")
        max_length = info.get("max_length")

        if data_type in INTEGER_TYPES:
            try:
                int(value)
            except (TypeError, ValueError):
                errors.append(f"{label} must be a number.")

        if data_type in DATE_TYPES:
            try:
                date.fromisoformat(str(value))
            except ValueError:
                errors.append(f"{label} must be a valid date.")

        if column in BOOLEAN_FIELDS and not validate_boolean(column, raw_value):
            errors.append(f"{label} must be true/false or 1/0.")

        if max_length and isinstance(value, str) and len(value) > max_length:
            errors.append(f"{label} must be {max_length} characters or fewer.")

    return errors


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


def duplicate_row_exists(config, columns, exclude_pk_values=None):
    compare_columns = config.get("unique_fields") or [
        column
        for column in columns
        if not (config["auto_pk"] and column in config["pk"])
    ]
    values = [get_form_value(column) for column in compare_columns]
    where_clause = sql.SQL(" AND ").join(
        sql.SQL("{} IS NOT DISTINCT FROM %s").format(sql.Identifier(column))
        for column in compare_columns
    )

    if exclude_pk_values:
        pk_clause = sql.SQL(" AND ").join(
            sql.SQL("{} <> %s").format(sql.Identifier(column))
            for column in config["pk"]
        )
        where_clause = sql.SQL("({}) AND ({})").format(where_clause, pk_clause)
        values += exclude_pk_values

    conn, cur = get_cursor()
    try:
        cur.execute(
            sql.SQL("SELECT 1 FROM {} WHERE {} LIMIT 1").format(
                sql.Identifier(config["table"]), where_clause
            ),
            values,
        )
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def update_row(config, columns):
    pk_values = [get_form_value(column) for column in config["pk"]]
    update_columns = [
        column
        for column in columns
        if column not in config["pk"] and get_raw_form_value(column) is not None
    ]

    if not update_columns or any(value is None for value in pk_values):
        return 0

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
        rowcount = cur.rowcount
        conn.commit()
        return rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def delete_row(config):
    pk_values = [get_form_value(column) for column in config["pk"]]
    if any(value is None for value in pk_values):
        return 0

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
        rowcount = cur.rowcount
        conn.commit()
        return rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def render_table(config):
    rows, fields = fetch_all(config)
    return render_template(
        "search_and_show_list.html",
        res=rows,
        fields=fields,
        title=f"{config.get('display', config['table']).title()} Details",
    )


def render_add_page(alias, error_messages=None):
    config = get_config(alias)
    fields = get_columns(config["table"])
    if config["auto_pk"]:
        fields = [field for field in fields if field not in config["pk"]]
    metadata = get_column_info(config["table"])
    required_fields = [
        field
        for field in fields
        if not metadata.get(field, {}).get("nullable", True)
    ]
    return render_template(
        "add_page.html",
        id=alias.lower(),
        display_name=config.get("display", alias).title(),
        fields=fields,
        required_fields=required_fields,
        error_messages=error_messages or [],
    )


def render_update_lookup(alias, error_messages=None, values=None):
    config = get_config(alias)
    return render_template(
        "update_lookup.html",
        alias=alias.lower(),
        display_name=config.get("display", alias).title(),
        pk_fields=config["pk"],
        error_messages=error_messages or [],
        values=values or {},
    )


def render_update_form(alias, fields, row, error_messages=None):
    config = get_config(alias)
    metadata = get_column_info(config["table"])
    required_fields = [
        field
        for field in fields
        if field in config["pk"] or not metadata.get(field, {}).get("nullable", True)
    ]
    values = dict(zip(fields, row))
    return render_template(
        "update_form.html",
        alias=alias.lower(),
        display_name=config.get("display", alias).title(),
        fields=fields,
        pk_fields=config["pk"],
        required_fields=required_fields,
        values=values,
        error_messages=error_messages or [],
    )


def render_update_page(alias):
    return render_update_lookup(alias)


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
        deleted = delete_row(config)
        if deleted:
            flash("User deleted successfully.", "success")
        else:
            flash("User was not found.", "warning")
        return redirect(url_for("show_users"))

    if "update" in request.form:
        return render_update_form("user", fields, row)

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
        validation_errors = validate_form(config, fields, "insert")
        if validation_errors:
            return render_add_page(alias, validation_errors), 400
        if config.get("unique_fields") and duplicate_row_exists(config, fields):
            return (
                render_add_page(
                    alias,
                    [f"A {config.get('display', 'record').lower()} with these unique details already exists."],
                ),
                400,
            )
        try:
            insert_row(config, fields)
        except psycopg2.Error as error:
            return render_add_page(alias, [database_error_message(error)]), 400
        flash(f"{config.get('display', alias).title()} added successfully.", "success")
        return render_table(config)
    return render_add_page(alias)


# ================= UPDATE =================
@app.route("/update_<alias>_page", methods=["GET", "POST"])
@login_required
def update_page(alias):
    config = get_config(alias)
    if request.method == "POST" and any(get_raw_form_value(field) for field in config["pk"]):
        pk_values = [get_form_value(field) for field in config["pk"]]
        if any(value is None for value in pk_values):
            return render_update_lookup(
                alias,
                ["Enter every ID field before fetching the record."],
                {field: get_raw_form_value(field) or "" for field in config["pk"]},
            ), 400

        row, fields = fetch_one(config, pk_values)
        if row is None:
            return render_update_lookup(
                alias,
                [f"{config.get('display', alias).title()} was not found."],
                {field: get_raw_form_value(field) or "" for field in config["pk"]},
            ), 404
        return render_update_form(alias, fields, row)

    return render_update_page(alias)


@app.route("/update_<alias>_details", methods=["POST"])
@login_required
def update_details_for_alias(alias):
    config = get_config(alias)
    fields = get_columns(config["table"])
    validation_errors = validate_form(config, fields, "update")
    pk_values = [get_form_value(field) for field in config["pk"]]
    if config.get("unique_fields") and not validation_errors:
        if duplicate_row_exists(config, fields, exclude_pk_values=pk_values):
            validation_errors.append(
                f"A {config.get('display', 'record').lower()} with these unique details already exists."
            )
    if validation_errors:
        return (
            render_update_form(
                alias,
                fields,
                [get_form_value(field) for field in fields],
                validation_errors,
            ),
            400,
        )
    try:
        updated = update_row(config, fields)
    except psycopg2.Error as error:
        return (
            render_update_form(
                alias,
                fields=fields,
                row=[get_form_value(field) for field in fields],
                error_messages=[database_error_message(error)],
            ),
            400,
        )
    if updated:
        flash(f"{config.get('display', alias).title()} updated successfully.", "success")
    else:
        flash(f"{config.get('display', alias).title()} was not found.", "warning")
    return render_table(config)


@app.route("/update_details", methods=["POST"])
@login_required
def update_details():
    config = get_config("user")
    fields = get_columns(config["table"])
    validation_errors = validate_form(config, fields, "update")
    pk_values = [get_form_value(field) for field in config["pk"]]
    if not validation_errors and duplicate_row_exists(config, fields, exclude_pk_values=pk_values):
        validation_errors.append("A user with these unique details already exists.")
    if validation_errors:
        return (
            render_update_form(
                "user",
                fields,
                [get_form_value(field) for field in fields],
                validation_errors,
            ),
            400,
        )
    try:
        updated = update_row(config, fields)
    except psycopg2.Error as error:
        return (
            render_update_form(
                "user",
                fields,
                [get_form_value(field) for field in fields],
                [database_error_message(error)],
            ),
            400,
        )
    if updated:
        flash("User updated successfully.", "success")
    else:
        flash("User was not found.", "warning")
    return redirect(url_for("show_users"))


# ================= DELETE =================
@app.route("/remove_<alias>", methods=["GET", "POST"])
@login_required
def remove_page(alias):
    config = get_config(alias)
    return render_template(
        "remove_page.html",
        alias=alias.lower(),
        display_name=config.get("display", alias).title(),
        pk_fields=config["pk"],
    )


@app.route("/del_<alias>", methods=["POST"])
@login_required
def delete_details(alias):
    config = get_config(alias)
    try:
        deleted = delete_row(config)
    except psycopg2.Error as error:
        flash(database_error_message(error), "danger")
        return render_template(
            "remove_page.html",
            alias=alias.lower(),
            display_name=config.get("display", alias).title(),
            pk_fields=config["pk"],
        ), 400
    if deleted:
        flash(f"{config.get('display', alias).title()} deleted successfully.", "success")
    else:
        flash(f"{config.get('display', alias).title()} was not found.", "warning")
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
