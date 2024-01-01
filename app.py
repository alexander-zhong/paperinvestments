import os

# Yahoo finance API 
import yfinance
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from sqlite3 import connect
from werkzeug.security import check_password_hash, generate_password_hash
import requests
from functools import wraps

# Standard Configuration of the flask application
app = Flask(__name__)


# Configuration of session to use filesystem instead of signed cookies to prevent client side attacks
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

# Configures the routes so if not login, it will redirect back to login
def login_required(f):
    @wraps(f)
    def check_login(*args, **kwargs):
        if session.get("user_id") == None:
            return redirect("/login")
        return f(*args, **kwargs)
    return check_login


# Ensure webpage provides most updated info
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Injects the username into layout.html
@app.context_processor
def inject_username():
    username = None
    if "username" in session:
        username = session["username"]
    return dict(username=username)




# Logins the user
@app.route("/login", methods=["GET", "POST"])
def login():
    
    # Delete all session data before proceeding in case user was already logged in
    session.clear()

    # POST method
    if request.method == "POST":

        # Connects to SQL database
        db = connect("paperinvestments.db")
        cursor = db.cursor()

        # Ensure username and password was submitted
        if not request.form.get("username"):
            return render_template("login.html", username=False, password=False, invalid=False)
        elif not request.form.get("password"):
            return render_template("login.html", username=True, password=False, invalid=False)

        # Finds if username exist
        cursor.execute("SELECT * FROM users WHERE username = (?)" , (request.form.get("username"),))
        user_info = cursor.fetchone()


        # If username does not exist or password is wrong, return error message
        if user_info == None or not check_password_hash(user_info[3], request.form.get("password")):
            return render_template("login.html", username=True, password=True, invalid=True)

        # Save session data for application use
        session["user_id"] = user_info[0]
        session["username"] = user_info[1]

        # Closes the cursor
        cursor.close()
        db.close()

        # Redirect user their portfolio
        return redirect("/home")

    # GET method
    else:
        # Username/Password set to true only to prevent alert from showing before user enters any details 
        return render_template("login.html", username=True, password=True, invalid=False)
    


# Registers the user
@app.route("/register", methods=["GET", "POST"])
def register():

    # Clears the session before we register
    session.clear()

    if request.method == "POST":
        
        # Gather form information 
        usr_username = request.form.get("username")
        usr_email = request.form.get("email")
        usr_password = request.form.get("password")
        usr_confirm = request.form.get("confirmpassword")

        # Checking the required fields are filled out
        if not usr_username:
            return render_template("register.html", username=False, email=False, password=False, confirmpassword=False)
        elif not usr_email:
            return render_template("register.html", username=True, email=False, password=False, confirmpassword=False)
        elif not usr_password:
            return render_template("register.html", username=True, email=True, password=False, confirmpassword=False)
        elif usr_password != usr_confirm:
            return render_template("register.html", username=True, email=True, password=True, confirmpassword=False)
        else:
            # Checks if username is already in the database
            db = connect("paperinvestments.db")
            cursor = db.cursor()

            cursor.execute("SELECT * FROM USERS where username = (?)", (usr_username, ))
            db_usernames = cursor.fetchall()

    
            if len(db_usernames) != 0:
                return render_template("register.html", username=False, email=False, password=False, confirmpassword=False)
        

            password_hash = generate_password_hash(usr_password)

            # Inserts the new user into our database
            cursor.execute("INSERT INTO users (username, email, hash) VALUES (?, ?, ?)", (usr_username, usr_email, password_hash))
            cursor.close()

            cursor2 = db.cursor()
            cursor2 = db.execute("SELECT * FROM USERS where username = (?)", (usr_username, ))

            # Info of the user
            info = cursor2.fetchone()

            # Remember which user has logged in and include their information
            session["user_id"] = info[0]
            session["username"] = info[1]
        
            # Commits into our database
            db.commit()

            # Closes the connection to our database
            cursor.close()
            db.close()
        

            return redirect("/home")


    return render_template("register.html", username=True, email=True, password=True, confirmpassword=True)


# Logs the user out
@app.route("/logout")
def logout():
    # Clear any session data
    session.clear()

    # Redirect user to login form
    return redirect("/login")



# Displays the porfolio of the user
@app.route("/home")
@login_required
def home():
    # Connects database    
    db = connect("paperinvestments.db")
    cursor = db.cursor()
    
    # Finds all the stock data of the user
    cursor.execute("SELECT * FROM assets WHERE id = (?)", (session["user_id"],))
    stock_data = cursor.fetchall()
    cursor.close()
    
    # Finds the cash data of the user
    cursor2 = db.cursor()
    cursor2.execute("SELECT * FROM users WHERE id = (?)", (session["user_id"], ))
    user_info = cursor2.fetchone()
    cash = user_info[4]
    
    cursor2.close()
    db.close()
    
    updated_stock_data = []
    
    total_liquidity = cash
    
    if len(stock_data) == 0:
        updated_stock_data = []
    else:
        for stock in stock_data:
            # Get a dict of the data from yahoo API
            ticker_object = yfinance.Ticker(stock[1])
            ticker_info = ticker_object.info
            price_per_share = ticker_info["currentPrice"]
            total_value = price_per_share * stock[2]
            total_liquidity += total_value
            
            updated_stock_data.append([stock[1], stock[2], price_per_share, total_value])
    
    return render_template("home.html", stock_data=updated_stock_data, cash=cash, total_liquidity=total_liquidity)
 
 
# Redirects to home if they are logged in
@app.route("/")
@login_required
def index():
    return redirect("/home")


# Lets users buy/sell their stocks
@app.route("/trade", methods=["GET", "POST"])
@login_required
def trade():
    
    if request.method == "POST":
        
        
        button_value = request.form["submit_button"]
        print(button_value)
        # Checks if the user pressed buy or sell when submitting the form (usually if users alter the frontend this would happen)
        if button_value != "buy" and button_value != "sell":
            return render_template("trade.html", error="Please choose buy or sell", success=None)
        
        
        ticker = request.form.get("ticker")
        number_of_shares = request.form.get("number_of_shares")
        if not number_of_shares:
            return render_template("trade.html", error="Please input number of shares you would like to " + str(button_value)  + "!", success=None)
        elif not ticker:
            return render_template("trade.html", error="Please input a ticker symbol!", success=None)
            
        number_of_shares = int(number_of_shares)
            
        # Checks if inputted shares is negative 
        if number_of_shares < 0:
            return render_template("trade.html", error="Please input a positive amount of shares!", success=None)
        elif float(request.form.get("number_of_shares")) != number_of_shares:
            return render_template("trade.html", error="Please input a whole number!", success=None)
        elif number_of_shares == 0:
            return render_template("trade.html", error="Cannot be zero shares!", success=None)     
    

        if button_value == "buy":

            try:
                # Connects to database and creates a cursor
                db = connect("paperinvestments.db")
                cursor = db.cursor()
            
                # Finds the current cash value
                cursor.execute("SELECT * FROM users WHERE id = (?)", (session["user_id"],))
                user_info = cursor.fetchone()
            
                cash_amount = user_info[4]
            
                # Get a dict of the data from yahoo API
                ticker_object = yfinance.Ticker(ticker)
                ticker_info = ticker_object.info
                
                
                # Checks if we have data on it yet
                if "currentPrice" not in ticker_info:
                    return render_template("trade.html", error="Sorry, we don't have data on that just yet!", success=None)
                
                total_cost = round(ticker_object.info["currentPrice"] * number_of_shares, 2)
                
                if total_cost > cash_amount:
                    return render_template("trade.html", error="Not enough money in your account!", success=None)
                
                # Close current cursor
                cursor.close()
                
                
                current_cash = cash_amount - total_cost
                

                # new cursor for inserting and updating tables
                cursor2 = db.cursor()
                
                cursor2.execute("UPDATE users SET cash = (?) WHERE id = (?)", (current_cash, session["user_id"]))
                
                
                """Checking if the stocks is already in stocks"""
                
                # new cursor for getting information
                cursor3 = db.cursor()
                stock_info = cursor3.execute("SELECT * FROM assets WHERE id = (?) AND symbol = (?) ", (session["user_id"], ticker)).fetchone()
                
                # Checks if already has it in assets, if not make a new row, if true, adds the number of shares to new table
                if stock_info == None:
                    cursor2.execute("INSERT INTO assets (id, symbol, shares) VALUES (?, ?, ?)", (session["user_id"], ticker, number_of_shares))
                else:
                    cursor2.execute("UPDATE assets SET shares = (?) WHERE id = (?) AND symbol = (?)", ((number_of_shares + stock_info[2]), session["user_id"], ticker))
                
                
                # adds to the history
                current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                cursor2.execute("INSERT INTO history (id, symbol, shares, total, pershare, date) VALUES (?, ?, ?, ?, ?, ?)", (session["user_id"], ticker, number_of_shares, total_cost, ticker_object.info["currentPrice"], current_date))

                success_message = "You have successfully bought " + str(number_of_shares) + " shares of " + str(ticker) + ", with a price of $" + str(ticker_object.info["currentPrice"]) + " per share and total transaction of $" + str(total_cost) + "!"
                
                # Closes all the connections and cursors
                db.commit()
                cursor2.close()
                cursor3.close()
                db.close()
                 
                return render_template("trade.html", error=None, success=success_message)            
            
            except requests.exceptions.HTTPError:
                return render_template("trade.html", error="Not a valid ticker symbol!", success=None)

            
        else:
            
            try:
                # Connects to database and creates a cursor
                db = connect("paperinvestments.db")
                cursor = db.cursor()
            
                # Finds the current cash value
                cursor.execute("SELECT * FROM users WHERE id = (?)", (session["user_id"],))
                user_info = cursor.fetchone()
                # Close current cursor
                cursor.close()
            
                cash_amount = user_info[4]
            
                # Get a dict of the data from yahoo API
                ticker_object = yfinance.Ticker(ticker)
                ticker_info = ticker_object.info
                
                # Checks if we have data on it yet
                if "currentPrice" not in ticker_info:
                    return render_template("trade.html", error="Sorry, we don't have data on that just yet!", success=None)
                
                total_cost = round(ticker_object.info["currentPrice"] * number_of_shares, 2)
                current_cash = cash_amount + total_cost
                
                shares_cursor = db.cursor()
                shares_cursor.execute("SELECT * FROM assets WHERE id = (?) AND symbol = (?)", (session["user_id"], ticker))
                stock_currently_have_info = shares_cursor.fetchone()
                shares_cursor.close()
                
                if stock_currently_have_info == None:
                    return render_template("trade.html", error="You don't have any shares of the stock!", success=None)
                elif stock_currently_have_info[2] < number_of_shares:
                    error_message = "You only have " + str(stock_currently_have_info[2]) + " shares of " + ticker + "!"
                    return render_template("trade.html", error=error_message, success=None)
                elif stock_currently_have_info[2] == number_of_shares:
                    updater = db.cursor()
                    updater.execute("DELETE FROM assets WHERE id = (?) AND symbol = (?)", (session["user_id"], ticker))
                    updater.close()
                elif stock_currently_have_info[2] > number_of_shares:
                    updater = db.cursor()
                    updater.execute("UPDATE assets SET shares = (?) WHERE id = (?) and symbol = (?)", ((stock_currently_have_info[2] - number_of_shares), session["user_id"], ticker))
                    updater.close()
                    
                # new cursor for inserting and updating tables
                cursor2 = db.cursor() 
                
                cursor2.execute("UPDATE users SET cash = (?) WHERE id = (?)", (current_cash, session["user_id"]))
                
                
                # adds to the history
                current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # make number of shares negative to demonstrate a subtraction of shares (selling)
                cursor2.execute("INSERT INTO history (id, symbol, shares, total, pershare, date) VALUES (?, ?, ?, ?, ?, ?)", (session["user_id"], ticker, -number_of_shares, total_cost, ticker_object.info["currentPrice"], current_date))

                success_message = "You have successfully sold " + str(number_of_shares) + " shares of " + str(ticker) + ", with a price of $" + str(ticker_object.info["currentPrice"]) + " per share and total transaction of $" + str(total_cost) + "!"
                
                # Closes all the connections and cursors
                db.commit()
                cursor2.close()
                db.close()
                 
                return render_template("trade.html", error=None, success=success_message)            
            
            except requests.exceptions.HTTPError:
                return render_template("trade.html", error="Not a valid ticker symbol!", success=None)
        
    
    return render_template("trade.html", error=None, success=None)


# Shows a list of history of user's transactions
@app.route("/history")
@login_required
def history():

    # Connects database    
    db = connect("paperinvestments.db")
    cursor = db.cursor()
    
    # Finds all the history of the user
    cursor.execute("SELECT * FROM history WHERE id = (?)", (session["user_id"],))
    
    print(session["user_id"])
    
    history = cursor.fetchall()
    history.reverse()
    return render_template("history.html", history=history) 




# Gather stock quotes and information about the stock
@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    
    if request.method == "POST":
        
        ticker_name = request.form.get("ticker")
        
        # Checks if user inputted a ticker symbol
        if not ticker_name:
            return render_template("quote.html", chosen=False, found=False)
        
        # try to find the ticker or else, return error
        try:
            
            # Get a dict of the data from yahoo API
            ticker_object = yfinance.Ticker(ticker_name)
            ticker_info = ticker_object.info
            
            return render_template("quote.html", chosen=True, found=True, info=ticker_info)            
            
        except requests.exceptions.HTTPError:
            return render_template("quote.html", chosen=False, found=False)
    
    return render_template("quote.html", chosen=True, found=False)
    
    



