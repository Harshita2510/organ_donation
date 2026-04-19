from flask import Flask, render_template, session, request, redirect, url_for
import psycopg2

app = Flask(__name__)
app.secret_key = "secret"

# ================= DB HELPER =================
def get_cursor():
    conn = psycopg2.connect(
    host="localhost",
    port=5433,
    database="forensic",
    user="postgres"
)
    return conn, conn.cursor()

# ================= HOME =================
@app.route("/")
@app.route("/home")
def home():
    if not session.get("login"):
        return redirect(url_for("login"))
    return render_template("home.html", username=session.get("username"))

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn, cur = get_cursor()
        cur.execute("SELECT * FROM public.login WHERE username = %s", (username,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        if res and res[1] == password:
            session["login"] = True
            session["username"] = username
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

# ================= ADD USER =================
@app.route("/add_user", methods=["GET", "POST"])
def add_user():
    if not session.get("login"):
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form["name"]
        dob = request.form["date_of_birth"]
        insurance = request.form.get("medical_insurance")
        insurance = True if insurance == "1" else False
        conn, cur = get_cursor()
        cur.execute(
            "INSERT INTO users (name, date_of_birth, medical_insurance) VALUES (%s, %s, %s)",
            (name, dob, insurance)
        )
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("show_users"))
    return render_template("add_page.html")

# ================= SHOW USERS =================
@app.route("/show_users")
def show_users():
    if not session.get("login"):
        return redirect(url_for("login"))
    conn, cur = get_cursor()
    cur.execute("SELECT * FROM users")
    res = cur.fetchall()
    fields = [desc[0] for desc in cur.description]
    cur.close()
    conn.close()
    return render_template("search_and_show_list.html", res=res, fields=fields)

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)