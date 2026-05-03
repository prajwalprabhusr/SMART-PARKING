import math
import os
import random
import tempfile
import time
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from urllib.parse import quote

from PIL import Image, ImageTk
import qrcode

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A6, landscape, legal
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_CONNECTOR_AVAILABLE = True
except ImportError:
    mysql = None
    Error = Exception
    MYSQL_CONNECTOR_AVAILABLE = False

# --- CONFIGURATION ---
UPI_ID = "8904132286-2@ybl"   # Payment UPI ID
PARKING_RATE_PER_HOUR = 20    # Rate in INR per hour
BASE_PARKING_HOURS = 3
BASE_PARKING_AMOUNT = 50

# Update these to match your MySQL setup
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "parking",
}

APP_BG = "#0b1220"
CARD_BG = "#121a2b"
PANEL_BG = "#182338"
INPUT_BG = "#0f1727"
TEXT_COLOR = "#eef4ff"
MUTED_TEXT = "#a9b7d0"
TITLE_COLOR = "#7dd3fc"
SUCCESS_TEXT = "#86efac"
WARNING_COLOR = "#fbbf24"
TABLE_HEADER_BG = "#22314d"
TABLE_ROW_BG = "#132033"
TABLE_ALT_BG = "#0f1b2d"
ACCENT_BLUE = "#0ea5e9"
ACCENT_PURPLE = "#8b5cf6"
ACCENT_GREEN = "#22c55e"
ACCENT_ORANGE = "#f97316"
ACCENT_GRAY = "#64748b"
ACCENT_PINK = "#ec4899"


class SmartParking:
    def __init__(self, root):
        self.root = root
        self.root.title("Shivamoga City Parking")
        self.root.configure(bg=APP_BG)
        self.set_app_icon()
        self.root.iconify()
        self.root.state("zoomed")

        self.db_connection = None
        self.connect_database()

        self.vehicle_types = ["Two Wheeler", "Four Wheeler"]
        self.current_vehicle = tk.StringVar(value="Two Wheeler")

        self.parking_data = {
            "Two Wheeler": {
                "blocks": {ch: {"rows": 2, "cols": 60} for ch in "ABCDEF"},
            },
            "Four Wheeler": {
                "blocks": {
                    **{ch: {"rows": 2, "cols": 60} for ch in "ABCDE"},
                    **{ch: {"rows": 2, "cols": 30} for ch in "FGH"},
                }
            }
        }

        self.parking_status = {}
        self.spot_details = {}

        for vehicle in self.vehicle_types:
            self.parking_status[vehicle] = {}
            self.spot_details[vehicle] = {}
            for block, info in self.parking_data[vehicle]["blocks"].items():
                total = info["rows"] * info["cols"]
                self.parking_status[vehicle][block] = {
                    "total": total,
                    "occupied": set(),
                }
                self.spot_details[vehicle][block] = {}

        self.load_active_bookings()

        self.create_header()
        self.summary_frame = tk.Frame(self.root, bg=CARD_BG, highlightthickness=1, highlightbackground=PANEL_BG)
        self.summary_frame.pack(pady=10)
        self.create_summary_table()

        self.display_frame = tk.Frame(self.root, bg=CARD_BG, highlightthickness=1, highlightbackground=PANEL_BG)
        self.display_frame.pack(fill="both", expand=True, padx=18, pady=12)
        self.show_blocks()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.deiconify()

    def set_app_icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parking_app.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

    def connect_database(self):
        if not MYSQL_CONNECTOR_AVAILABLE:
            print("MySQL connector not installed. Database features are disabled.")
            self.db_connection = None
            return

        try:
            base_connection = mysql.connector.connect(
                host=MYSQL_CONFIG["host"],
                user=MYSQL_CONFIG["user"],
                password=MYSQL_CONFIG["password"],
            )
            cursor = base_connection.cursor()
            cursor.execute("CREATE DATABASE IF NOT EXISTS parking")
            base_connection.commit()
            cursor.close()
            base_connection.close()

            self.db_connection = mysql.connector.connect(**MYSQL_CONFIG)
            self.create_details_table()
        except Error as err:
            self.db_connection = None
            print(f"Database connection failed: {err}")

    def create_details_table(self):
        if not self.db_connection:
            return

        query = """
        CREATE TABLE IF NOT EXISTS details (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticket_number VARCHAR(50) NOT NULL UNIQUE,
            vehicle_number VARCHAR(50) NOT NULL,
            phone_number VARCHAR(20) NOT NULL,
            vehicle_type VARCHAR(30) NOT NULL,
            entry_time DATETIME NOT NULL,
            exit_time DATETIME NULL,
            parking_position VARCHAR(100) NOT NULL,
            total_bill DECIMAL(10, 2) DEFAULT 0.00
        )
        """

        cursor = self.db_connection.cursor()
        cursor.execute(query)
        self.db_connection.commit()
        cursor.close()

    def parse_parking_position(self, parking_position):
        try:
            block_part, spot_part = parking_position.split(" - ")
            block = block_part.replace("Block", "").strip().upper()
            key = spot_part.strip().upper()
            return block, key
        except ValueError:
            return None, None

    def load_active_bookings(self):
        if not self.db_connection:
            return

        query = """
        SELECT ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, parking_position
        FROM details
        WHERE exit_time IS NULL
        """

        try:
            cursor = self.db_connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()

            for ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, parking_position in rows:
                block, key = self.parse_parking_position(parking_position)
                if not block or not key:
                    continue

                if vehicle_type not in self.parking_status:
                    continue

                if block not in self.parking_status[vehicle_type]:
                    continue

                self.parking_status[vehicle_type][block]["occupied"].add(key)
                self.spot_details[vehicle_type][block][key] = {
                    "ticket_number": ticket_number,
                    "vehicle_number": vehicle_number,
                    "phone_number": phone_number,
                    "entry_timestamp": entry_time.timestamp() if entry_time else time.time(),
                    "entry_datetime": entry_time if entry_time else datetime.now(),
                    "parking_position": parking_position,
                }
        except Error as err:
            print(f"Active booking load failed: {err}")

    def center_popup(self, window, width, height):
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x_pos = (screen_width - width) // 2
        y_pos = (screen_height - height) // 2
        window.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

    def style_entry(self, entry):
        entry.configure(
            bg=INPUT_BG,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            highlightthickness=1,
            highlightbackground=PANEL_BG,
            highlightcolor=TITLE_COLOR,
        )

    def create_header(self):
        header = tk.Label(
            self.root,
            text="SHIVAMOGA CITY PARKING",
            font=("Arial Black", 18),
            bg=APP_BG,
            fg=TITLE_COLOR,
        )
        header.pack(pady=10)

        top_frame = tk.Frame(self.root, bg=APP_BG)
        top_frame.pack()

        tk.Label(
            top_frame,
            text="Select Vehicle Type:",
            font=("Arial", 11, "bold"),
            bg=APP_BG,
            fg=TEXT_COLOR,
        ).pack(side="left")

        for vt in self.vehicle_types:
            tk.Radiobutton(
                top_frame,
                text=vt,
                variable=self.current_vehicle,
                value=vt,
                bg=APP_BG,
                fg=TEXT_COLOR,
                selectcolor=PANEL_BG,
                activebackground=APP_BG,
                activeforeground=TEXT_COLOR,
                font=("Arial", 10),
                command=self.show_blocks,
            ).pack(side="left", padx=5)

        tk.Button(
            top_frame,
            text="Show Blocks",
            bg=ACCENT_BLUE,
            fg="white",
            font=("Arial", 10, "bold"),
            activebackground="#38bdf8",
            command=self.show_blocks,
        ).pack(side="left", padx=10)

        tk.Button(
            top_frame,
            text="Departure / Free Spot",
            bg=ACCENT_ORANGE,
            fg="white",
            font=("Arial", 10, "bold"),
            activebackground="#fb923c",
            command=self.departure_window,
        ).pack(side="left", padx=10)

    def create_summary_table(self):
        for widget in self.summary_frame.winfo_children():
            widget.destroy()

        tk.Label(
            self.summary_frame,
            text="Parking Status Summary",
            font=("Arial", 12, "bold"),
            bg=CARD_BG,
            fg=TEXT_COLOR,
        ).pack()

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview.Heading",
            font=("Arial", 10, "bold"),
            background=TABLE_HEADER_BG,
            foreground=TEXT_COLOR,
        )
        style.configure(
            "Treeview",
            font=("Arial", 10),
            background=TABLE_ROW_BG,
            fieldbackground=TABLE_ROW_BG,
            foreground=TEXT_COLOR,
            bordercolor=PANEL_BG,
            rowheight=26,
        )
        style.map("Treeview", background=[("selected", ACCENT_BLUE)], foreground=[("selected", "white")])

        tree = ttk.Treeview(
            self.summary_frame,
            columns=("Vehicle", "Total", "Occupied", "Available"),
            show="headings",
            height=3,
        )

        tree.column("Vehicle", width=120, anchor="w")
        tree.column("Total", width=120, anchor="center")
        tree.column("Occupied", width=120, anchor="center")
        tree.column("Available", width=120, anchor="center")
        tree.heading("Vehicle", text="Vehicle Type")
        tree.heading("Total", text="Total Spots")
        tree.heading("Occupied", text="Occupied")
        tree.heading("Available", text="Available")

        for vehicle in self.vehicle_types:
            total = sum(self.parking_status[vehicle][b]["total"] for b in self.parking_status[vehicle])
            occupied = sum(len(self.parking_status[vehicle][b]["occupied"]) for b in self.parking_status[vehicle])
            available = total - occupied
            tree.insert("", "end", values=(vehicle, total, occupied, available))

        tree.pack(pady=5)

    def show_blocks(self):
        for widget in self.display_frame.winfo_children():
            widget.destroy()

        vehicle = self.current_vehicle.get()
        blocks = self.parking_status[vehicle]

        title = tk.Label(
            self.display_frame,
            text=f"{vehicle} Parking Blocks",
            font=("Arial", 13, "bold"),
            bg=CARD_BG,
            fg=SUCCESS_TEXT,
        )
        title.pack(pady=10)

        block_frame = tk.Frame(self.display_frame, bg=CARD_BG)
        block_frame.pack()

        for i, (block, info) in enumerate(blocks.items()):
            total = info["total"]
            occ = len(info["occupied"])
            available = total - occ
            color = "#ff6666" if available == 0 else ("#7be47b" if available / total > 0.5 else "#ffcc66")

            tk.Button(
                block_frame,
                text=f"{'2W' if vehicle == 'Two Wheeler' else '4W'} {block}\nAvailable: {available}/{total}",
                width=15,
                height=3,
                bg=color,
                activebackground=color,
                font=("Arial", 10, "bold"),
                command=lambda b=block: self.show_block_detail(b),
            ).grid(row=i // 4, column=i % 4, padx=10, pady=10)

        tk.Button(
            self.display_frame,
            text="Record",
            bg=ACCENT_PINK,
            fg="white",
            font=("Arial", 11, "bold"),
            activebackground="#f472b6",
            command=self.open_retrieve_window,
        ).pack(pady=20)

    def show_block_detail(self, block):
        for widget in self.display_frame.winfo_children():
            widget.destroy()

        vehicle = self.current_vehicle.get()
        info = self.parking_data[vehicle]["blocks"][block]
        status = self.parking_status[vehicle][block]

        tk.Label(
            self.display_frame,
            text=f"{vehicle} - Block {block}",
            font=("Arial", 14, "bold"),
            bg=CARD_BG,
            fg=TITLE_COLOR,
        ).pack(pady=10)

        grid_frame = tk.Frame(self.display_frame, bg=CARD_BG)
        grid_frame.pack()

        max_display_cols = 30

        for r in range(1, info["rows"] + 1):
            for c in range(1, info["cols"] + 1):
                key = f"R{r}C{c}"
                color = "#7be47b" if key not in status["occupied"] else "#ff6666"

                if c <= max_display_cols:
                    gui_row = r
                    gui_col = c
                else:
                    gui_row = r + info["rows"] + 1
                    gui_col = c - max_display_cols

                tk.Button(
                    grid_frame,
                    text=key,
                    width=5,
                    height=1,
                    bg=color,
                    activebackground=color,
                    command=lambda b=block, row=r, col=c: self.allot_spot(b, row, col),
                ).grid(row=gui_row, column=gui_col, padx=1, pady=1)

        if info["cols"] > max_display_cols:
            ttk.Separator(grid_frame, orient="horizontal").grid(
                row=info["rows"] + 1,
                column=0,
                columnspan=max_display_cols + 1,
                sticky="ew",
                pady=3,
            )

        tk.Button(
            self.display_frame,
            text="Back to Blocks",
            bg=ACCENT_BLUE,
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.show_blocks,
        ).pack(pady=15)

    def generate_ticket_number(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_part = random.randint(100, 999)
        return f"TKT{timestamp}{random_part}"

    def save_entry_to_db(self, ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, parking_position):
        if not self.db_connection:
            return

        query = """
        INSERT INTO details (
            ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, parking_position, total_bill
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            ticket_number,
            vehicle_number,
            phone_number,
            vehicle_type,
            entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            parking_position,
            0.00,
        )

        try:
            cursor = self.db_connection.cursor()
            cursor.execute(query, values)
            self.db_connection.commit()
            cursor.close()
        except Error as err:
            print(f"Insert failed: {err}")

    def update_exit_in_db(self, ticket_number, exit_time, total_bill):
        if not self.db_connection:
            return

        query = """
        UPDATE details
        SET exit_time = %s, total_bill = %s
        WHERE ticket_number = %s
        """

        values = (
            exit_time.strftime("%Y-%m-%d %H:%M:%S"),
            total_bill,
            ticket_number,
        )

        try:
            cursor = self.db_connection.cursor()
            cursor.execute(query, values)
            self.db_connection.commit()
            cursor.close()
        except Error as err:
            print(f"Update failed: {err}")

    def fetch_records_by_date(self, selected_date):
        if not self.db_connection:
            return []

        query = """
        SELECT ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, exit_time, parking_position, total_bill
        FROM details
        WHERE DATE(entry_time) = %s
        ORDER BY entry_time ASC
        """

        try:
            cursor = self.db_connection.cursor()
            cursor.execute(query, (selected_date,))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Error as err:
            print(f"Fetch failed: {err}")
            messagebox.showerror("Database Error", f"Could not retrieve records.\n{err}")
            return []

    def fetch_records_by_vehicle_number(self, vehicle_number):
        if not self.db_connection:
            return []

        query = """
        SELECT ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, exit_time, parking_position, total_bill
        FROM details
        WHERE UPPER(vehicle_number) = %s
        ORDER BY entry_time ASC
        """

        try:
            cursor = self.db_connection.cursor()
            cursor.execute(query, (vehicle_number.strip().upper(),))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Error as err:
            print(f"Fetch failed: {err}")
            messagebox.showerror("Database Error", f"Could not retrieve records.\n{err}")
            return []

    def build_pdf_table_data(self, records):
        table_data = [[
            "S.No",
            "Ticket No",
            "Vehicle No",
            "Phone No",
            "Vehicle Type",
            "Entry Time",
            "Exit Time",
            "Parking Position",
            "Total Bill",
        ]]

        for index, row in enumerate(records, start=1):
            ticket_number, vehicle_number, phone_number, vehicle_type, entry_time, exit_time, parking_position, total_bill = row
            table_data.append([
                str(index),
                str(ticket_number),
                str(vehicle_number),
                str(phone_number),
                str(vehicle_type),
                entry_time.strftime("%Y-%m-%d %H:%M:%S") if entry_time else "",
                exit_time.strftime("%Y-%m-%d %H:%M:%S") if exit_time else "",
                str(parking_position),
                f"Rs. {float(total_bill):.2f}" if total_bill is not None else "Rs. 0.00",
            ])

        return table_data

    def create_records_pdf(self, selected_date, records):
        safe_date = selected_date.replace("-", "_")
        file_path = os.path.join(tempfile.gettempdir(), f"parking_records_{safe_date}.pdf")
        styles = getSampleStyleSheet()

        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(legal),
            leftMargin=20,
            rightMargin=20,
            topMargin=20,
            bottomMargin=20,
        )

        elements = [
            Paragraph("SHIVAMOGA CITY PARKING", styles["Title"]),
            Spacer(1, 8),
            Paragraph(f"Record Date: {selected_date}", styles["Heading3"]),
            Spacer(1, 12),
        ]

        table = Table(
            self.build_pdf_table_data(records),
            repeatRows=1,
            colWidths=[35, 95, 90, 90, 85, 110, 110, 110, 70],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#052b84")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
        ]))

        elements.append(table)
        doc.build(elements)
        return file_path

    def create_ticket_pdf(self, vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt):
        file_path = os.path.join(tempfile.gettempdir(), f"ticket_{ticket_number}.pdf")
        styles = getSampleStyleSheet()

        doc = SimpleDocTemplate(
            file_path,
            pagesize=A6,
            leftMargin=18,
            rightMargin=18,
            topMargin=18,
            bottomMargin=18,
        )

        elements = [
            Paragraph("SHIVAMOGA CITY PARKING", styles["Title"]),
            Spacer(1, 10),
            Paragraph(f"<b>Ticket No:</b> {ticket_number}", styles["BodyText"]),
            Spacer(1, 6),
            Paragraph(f"<b>Vehicle No:</b> {vehicle_number}", styles["BodyText"]),
            Spacer(1, 6),
            Paragraph(f"<b>Phone No:</b> {phone_number}", styles["BodyText"]),
            Spacer(1, 6),
            Paragraph(f"<b>Vehicle Type:</b> {vehicle}", styles["BodyText"]),
            Spacer(1, 6),
            Paragraph(f"<b>Block:</b> {block}", styles["BodyText"]),
            Spacer(1, 6),
            Paragraph(f"<b>Spot ID:</b> {key}", styles["BodyText"]),
            Spacer(1, 6),
            Paragraph(
                f"<b>Entry Time:</b> {entry_dt.strftime('%d-%m-%Y %I:%M:%S %p')}",
                styles["BodyText"],
            ),
        ]

        doc.build(elements)
        return file_path

    def print_temp_file(self, file_path):
        try:
            os.startfile(file_path, "print")
            self.root.after(60000, lambda: self.cleanup_temp_file(file_path))
        except Exception as err:
            self.cleanup_temp_file(file_path)
            raise err

    def cleanup_temp_file(self, file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass

    def print_ticket(self, vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt):
        if not REPORTLAB_AVAILABLE:
            messagebox.showwarning(
                "Print Dependency Missing",
                "Install reportlab with: pip install reportlab\nThen ticket printing will work.",
            )
            return

        try:
            file_path = self.create_ticket_pdf(vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt)
            self.print_temp_file(file_path)
        except Exception as err:
            messagebox.showerror("Print Error", f"Could not print ticket.\n{err}")

    def normalize_indian_phone(self, phone_number):
        normalized_phone = "".join(ch for ch in phone_number if ch.isdigit())
        if len(normalized_phone) == 10:
            normalized_phone = f"91{normalized_phone}"
        return normalized_phone

    def open_whatsapp_message(self, phone_number, message_text):
        normalized_phone = self.normalize_indian_phone(phone_number)
        encoded_message = quote(message_text)
        whatsapp_app_url = f"whatsapp://send?phone={normalized_phone}&text={encoded_message}"
        whatsapp_web_url = f"https://wa.me/{normalized_phone}?text={encoded_message}"

        try:
            os.startfile(whatsapp_app_url)
        except OSError:
            try:
                webbrowser.open(whatsapp_web_url)
            except Exception as err:
                messagebox.showerror("WhatsApp Error", f"Could not open WhatsApp.\n{err}")

    def build_ticket_message(self, vehicle, block, key, vehicle_number, ticket_number, entry_dt):
        return (
            "Shivamoga City Parking\n"
            f"Ticket No: {ticket_number}\n"
            f"Vehicle No: {vehicle_number}\n"
            f"Vehicle Type: {vehicle}\n"
            f"Block: {block}\n"
            f"Spot ID: {key}\n"
            f"Entry Time: {entry_dt.strftime('%d-%m-%Y %I:%M:%S %p')}"
        )

    def send_ticket_to_whatsapp(self, vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt):
        message_text = self.build_ticket_message(vehicle, block, key, vehicle_number, ticket_number, entry_dt)
        self.open_whatsapp_message(phone_number, message_text)

    def build_departure_message(self, vehicle, block, key, vehicle_number, ticket_number, entry_dt, exit_dt, hours, amount):
        return (
            "Shivamoga City Parking\n"
            f"Parking Bill\n"
            f"Ticket No: {ticket_number}\n"
            f"Vehicle No: {vehicle_number}\n"
            f"Vehicle Type: {vehicle}\n"
            f"Block/Spot: {block}/{key}\n"
            f"Entry Time: {entry_dt.strftime('%d-%m-%Y %I:%M:%S %p')}\n"
            f"Exit Time: {exit_dt.strftime('%d-%m-%Y %I:%M:%S %p')}\n"
            f"Total Bill: Rs. {amount}"
        )

    def send_departure_to_whatsapp(self, vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt, exit_dt, hours, amount):
        message_text = self.build_departure_message(
            vehicle, block, key, vehicle_number, ticket_number, entry_dt, exit_dt, hours, amount
        )
        self.open_whatsapp_message(phone_number, message_text)

    def print_records(self, selected_date, records):
        if not records:
            messagebox.showwarning("Print Record", "No records available to print.")
            return

        if not REPORTLAB_AVAILABLE:
            messagebox.showwarning(
                "PDF Dependency Missing",
                "Install reportlab with: pip install reportlab\nThen PDF record printing will work.",
            )
            return

        try:
            file_path = self.create_records_pdf(selected_date, records)
            os.startfile(file_path)
            messagebox.showinfo("Print Record", f"PDF created successfully.\n{file_path}")
        except Exception as err:
            messagebox.showerror("Print Error", f"Could not print records.\n{err}")

    def open_retrieve_window(self):
        if not MYSQL_CONNECTOR_AVAILABLE:
            messagebox.showwarning(
                "Dependency Warning",
                "MySQL connector is not installed.\nInstall it with: pip install mysql-connector-python",
            )
            return

        if not self.db_connection:
            messagebox.showwarning(
                "Database Warning",
                "Database is not connected. Please check MYSQL_CONFIG values.",
            )
            return

        win = tk.Toplevel(self.root)
        win.title("Retrieve Parking Details")
        win.configure(bg=CARD_BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self.center_popup(win, 1220, 720)

        tk.Label(
            win,
            text="Retrieve Parking Details By Date",
            font=("Arial", 14, "bold"),
            bg=CARD_BG,
            fg=TITLE_COLOR,
        ).pack(pady=10)

        nav_frame = tk.Frame(win, bg=CARD_BG)
        nav_frame.pack(fill="x", padx=10, pady=8)

        content_frame = tk.Frame(win, bg=CARD_BG)
        content_frame.pack(pady=5)

        result_frame = tk.Frame(win, bg=CARD_BG)
        result_frame.pack(fill="both", expand=True, padx=15, pady=10)

        columns = (
            "ticket_number",
            "vehicle_number",
            "phone_number",
            "vehicle_type",
            "entry_time",
            "exit_time",
            "parking_position",
            "total_bill",
        )
        tree = ttk.Treeview(result_frame, columns=columns, show="headings")

        headings = {
            "ticket_number": "Ticket No",
            "vehicle_number": "Vehicle No",
            "phone_number": "Phone No",
            "vehicle_type": "Vehicle Type",
            "entry_time": "Entry Time",
            "exit_time": "Exit Time",
            "parking_position": "Parking Position",
            "total_bill": "Total Bill",
        }

        widths = {
            "ticket_number": 170,
            "vehicle_number": 130,
            "phone_number": 130,
            "vehicle_type": 120,
            "entry_time": 170,
            "exit_time": 170,
            "parking_position": 170,
            "total_bill": 100,
        }

        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="center")

        y_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(result_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.pack(side="top", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")
        current_records = []
        current_label = datetime.now().strftime("%Y-%m-%d")

        def load_records(records, empty_message, label_text):
            nonlocal current_records, current_label
            current_records = records
            current_label = label_text

            for item in tree.get_children():
                tree.delete(item)

            if not records:
                messagebox.showinfo("No Records", empty_message)
                return

            for row in records:
                formatted_row = list(row)
                formatted_row[4] = row[4].strftime("%d-%m-%Y %I:%M:%S %p") if row[4] else ""
                formatted_row[5] = row[5].strftime("%d-%m-%Y %I:%M:%S %p") if row[5] else ""
                formatted_row[7] = f"{float(row[7]):.2f}" if row[7] is not None else "0.00"
                tree.insert("", "end", values=formatted_row)

        def clear_content_frame():
            for widget in content_frame.winfo_children():
                widget.destroy()

        def close_record_window():
            win.destroy()

        def show_date_search():
            clear_content_frame()

            form_frame = tk.Frame(content_frame, bg=CARD_BG)
            form_frame.pack(pady=5)

            tk.Label(
                form_frame,
                text="Enter Date (YYYY-MM-DD):",
                font=("Arial", 11, "bold"),
                bg=CARD_BG,
                fg=TEXT_COLOR,
            ).pack(side="left", padx=5)

            date_entry_local = tk.Entry(form_frame, width=18, font=("Arial", 11))
            self.style_entry(date_entry_local)
            date_entry_local.pack(side="left", padx=5)
            date_entry_local.insert(0, datetime.now().strftime("%Y-%m-%d"))
            date_entry_local.focus_set()

            tk.Button(
                form_frame,
                text="Search",
                bg=ACCENT_BLUE,
                fg="white",
                font=("Arial", 10, "bold"),
                command=lambda: search_records_with_value(date_entry_local.get().strip()),
            ).pack(side="left", padx=8)

            tk.Button(
                form_frame,
                text="Print Record",
                bg=ACCENT_GREEN,
                fg="white",
                font=("Arial", 10, "bold"),
                command=lambda: print_records_for_date(date_entry_local.get().strip()),
            ).pack(side="left", padx=8)

            date_entry_local.bind("<Return>", lambda event: search_records_with_value(date_entry_local.get().strip()))

        def show_vehicle_search():
            clear_content_frame()

            form_frame = tk.Frame(content_frame, bg=CARD_BG)
            form_frame.pack(pady=5)

            tk.Label(
                form_frame,
                text="Enter Vehicle No:",
                font=("Arial", 11, "bold"),
                bg=CARD_BG,
                fg=TEXT_COLOR,
            ).pack(side="left", padx=5)

            vehicle_entry_local = tk.Entry(form_frame, width=18, font=("Arial", 11))
            self.style_entry(vehicle_entry_local)
            vehicle_entry_local.pack(side="left", padx=5)
            vehicle_entry_local.focus_set()

            tk.Button(
                form_frame,
                text="Search",
                bg=ACCENT_PURPLE,
                fg="white",
                font=("Arial", 10, "bold"),
                command=lambda: search_vehicle_with_value(vehicle_entry_local.get().strip()),
            ).pack(side="left", padx=8)

            tk.Button(
                form_frame,
                text="Print Record",
                bg=ACCENT_GREEN,
                fg="white",
                font=("Arial", 10, "bold"),
                command=lambda: print_records_for_vehicle(vehicle_entry_local.get().strip()),
            ).pack(side="left", padx=8)

            vehicle_entry_local.bind("<Return>", lambda event: search_vehicle_with_value(vehicle_entry_local.get().strip()))

        def search_records_with_value(selected_date):
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date", "Please enter date in YYYY-MM-DD format.")
                return

            records = self.fetch_records_by_date(selected_date)
            load_records(records, f"No parking details found for {selected_date}.", selected_date)

        def search_vehicle_with_value(vehicle_number):
            vehicle_number = vehicle_number.strip().upper()
            if not vehicle_number:
                messagebox.showerror("Invalid Vehicle Number", "Please enter a vehicle number.")
                return

            records = self.fetch_records_by_vehicle_number(vehicle_number)
            load_records(records, f"No parking details found for vehicle number {vehicle_number}.", f"Vehicle {vehicle_number}")

        def print_records_for_date(selected_date):
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date", "Please enter date in YYYY-MM-DD format.")
                return

            records = self.fetch_records_by_date(selected_date)
            load_records(records, f"No parking details found for {selected_date}.", selected_date)
            if records:
                self.print_records(selected_date, records)

        def print_records_for_vehicle(vehicle_number):
            vehicle_number = vehicle_number.strip().upper()
            if not vehicle_number:
                messagebox.showerror("Invalid Vehicle Number", "Please enter a vehicle number.")
                return

            records = self.fetch_records_by_vehicle_number(vehicle_number)
            load_records(records, f"No parking details found for vehicle number {vehicle_number}.", f"Vehicle {vehicle_number}")
            if records:
                self.print_records(f"Vehicle {vehicle_number}", records)

        tk.Button(
            nav_frame,
            text="Back",
            bg=ACCENT_GRAY,
            fg="white",
            font=("Arial", 11, "bold"),
            width=12,
            activebackground="#94a3b8",
            command=close_record_window,
        ).pack(side="left", anchor="w")

        tk.Button(
            nav_frame,
            text="Search By Date",
            bg=ACCENT_BLUE,
            fg="white",
            font=("Arial", 11, "bold"),
            width=22,
            activebackground="#38bdf8",
            command=show_date_search,
        ).pack(side="left", padx=10)

        tk.Button(
            nav_frame,
            text="Search By Vehicle Number",
            bg=ACCENT_PURPLE,
            fg="white",
            font=("Arial", 11, "bold"),
            width=24,
            activebackground="#a78bfa",
            command=show_vehicle_search,
        ).pack(side="left", padx=10)

        show_date_search()

    def prompt_vehicle_details(self):
        result = {"vehicle_number": None, "phone_number": None}

        win = tk.Toplevel(self.root)
        win.title("Vehicle Details")
        win.configure(bg=CARD_BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self.center_popup(win, 430, 240)

        tk.Label(
            win,
            text="Enter Vehicle Details",
            font=("Arial", 13, "bold"),
            bg=CARD_BG,
            fg=TITLE_COLOR,
        ).pack(pady=12)

        form_frame = tk.Frame(win, bg=CARD_BG)
        form_frame.pack(pady=10)

        tk.Label(form_frame, text="Vehicle Number:", font=("Arial", 10, "bold"), bg=CARD_BG, fg=TEXT_COLOR).grid(row=0, column=0, padx=8, pady=8, sticky="e")
        vehicle_entry = tk.Entry(form_frame, width=22, font=("Arial", 10))
        self.style_entry(vehicle_entry)
        vehicle_entry.grid(row=0, column=1, padx=8, pady=8)

        tk.Label(form_frame, text="Phone Number:", font=("Arial", 10, "bold"), bg=CARD_BG, fg=TEXT_COLOR).grid(row=1, column=0, padx=8, pady=8, sticky="e")
        phone_entry = tk.Entry(form_frame, width=22, font=("Arial", 10))
        self.style_entry(phone_entry)
        phone_entry.grid(row=1, column=1, padx=8, pady=8)

        def submit_details(event=None):
            vehicle_number = vehicle_entry.get().strip().upper()
            phone_number = phone_entry.get().strip()

            if not vehicle_number:
                messagebox.showerror("Error", "Vehicle number is required.", parent=win)
                vehicle_entry.focus_set()
                return

            if not phone_number:
                messagebox.showerror("Error", "Phone number is required.", parent=win)
                phone_entry.focus_set()
                return

            if not phone_number.isdigit() or len(phone_number) != 10:
                messagebox.showerror("Error", "Phone number must contain exactly 10 digits.", parent=win)
                phone_entry.focus_set()
                return

            result["vehicle_number"] = vehicle_number
            result["phone_number"] = phone_number
            win.destroy()

        def close_window():
            win.destroy()

        button_frame = tk.Frame(win, bg=CARD_BG)
        button_frame.pack(pady=12)

        tk.Button(
            button_frame,
            text="OK",
            bg=ACCENT_BLUE,
            fg="white",
            font=("Arial", 10, "bold"),
            width=10,
            command=submit_details,
        ).pack(side="left", padx=8)

        tk.Button(
            button_frame,
            text="Cancel",
            bg=ACCENT_GRAY,
            fg="white",
            font=("Arial", 10, "bold"),
            width=10,
            command=close_window,
        ).pack(side="left", padx=8)

        vehicle_entry.bind("<Return>", lambda event: phone_entry.focus_set())
        phone_entry.bind("<Return>", submit_details)
        vehicle_entry.focus_set()

        win.wait_window(win)

        if result["vehicle_number"] is None or result["phone_number"] is None:
            return None

        return result["vehicle_number"], result["phone_number"]

    def allot_spot(self, block, row, col):
        vehicle = self.current_vehicle.get()
        key = f"R{row}C{col}"
        status = self.parking_status[vehicle][block]["occupied"]

        if key in status:
            messagebox.showerror("Error", "Spot already occupied!")
            return

        vehicle_details = self.prompt_vehicle_details()
        if vehicle_details is None:
            return
        vehicle_number, phone_number = vehicle_details

        status.add(key)
        ticket_number = self.generate_ticket_number()
        entry_dt = datetime.now()
        parking_position = f"Block {block} - {key}"

        self.spot_details[vehicle][block][key] = {
            "ticket_number": ticket_number,
            "vehicle_number": vehicle_number,
            "phone_number": phone_number,
            "entry_timestamp": time.time(),
            "entry_datetime": entry_dt,
            "parking_position": parking_position,
        }

        self.save_entry_to_db(ticket_number, vehicle_number, phone_number, vehicle, entry_dt, parking_position)

        self.create_summary_table()
        self.show_block_detail(block)
        self.send_ticket_to_whatsapp(vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt)
        self.show_allot_slip(vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt)

    def show_allot_slip(self, vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt):
        win = tk.Toplevel(self.root)
        win.title("Allotment Slip")
        win.configure(bg=CARD_BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self.center_popup(win, 460, 380)

        tk.Label(
            win,
            text="Parking Allotted",
            font=("Arial", 16, "bold"),
            fg=SUCCESS_TEXT,
            bg=CARD_BG,
        ).pack(pady=15)
        tk.Label(win, text=f"Ticket No: {ticket_number}", font=("Arial", 12, "bold"), bg=CARD_BG, fg=TEXT_COLOR).pack()
        tk.Label(win, text=f"Vehicle No: {vehicle_number}", font=("Arial", 12), bg=CARD_BG, fg=TEXT_COLOR).pack()
        tk.Label(win, text=f"Phone No: {phone_number}", font=("Arial", 12), bg=CARD_BG, fg=TEXT_COLOR).pack()
        tk.Label(win, text=f"Vehicle Type: {vehicle}", font=("Arial", 12), bg=CARD_BG, fg=TEXT_COLOR).pack()
        tk.Label(win, text=f"Block: {block}", font=("Arial", 12), bg=CARD_BG, fg=TEXT_COLOR).pack()
        tk.Label(win, text=f"Spot ID: {key}", font=("Arial", 12, "bold"), bg=CARD_BG, fg=TEXT_COLOR).pack()
        tk.Label(
            win,
            text=f"Entry Time: {entry_dt.strftime('%d-%m-%Y %I:%M:%S %p')}",
            font=("Arial", 11),
            bg=CARD_BG,
            fg=MUTED_TEXT,
        ).pack(pady=5)
        tk.Label(
            win,
            text="Please remember your ticket number!",
            font=("Arial", 9, "italic"),
            bg=CARD_BG,
            fg=MUTED_TEXT,
        ).pack()

        button_frame = tk.Frame(win, bg=CARD_BG)
        button_frame.pack(pady=20)

        tk.Button(
            button_frame,
            text="Print Token",
            bg=ACCENT_BLUE,
            fg="white",
            font=("Arial", 10, "bold"),
            command=lambda: self.print_ticket(
                vehicle, block, key, vehicle_number, phone_number, ticket_number, entry_dt
            ),
        ).pack(side="left", padx=6)

        tk.Button(
            button_frame,
            text="Close",
            bg=ACCENT_GRAY,
            fg="white",
            font=("Arial", 10, "bold"),
            command=win.destroy,
        ).pack(side="left", padx=6)
        win.wait_window(win)

    def departure_window(self):
        win = tk.Toplevel(self.root)
        win.title("Departure / Free Spot")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self.center_popup(win, 500, 520)

        tk.Label(
            win,
            text="Vehicle Departure",
            font=("Arial", 14, "bold"),
            bg=APP_BG,
            fg=WARNING_COLOR,
        ).pack(pady=10)

        v_type = tk.StringVar(value=self.current_vehicle.get())

        v_frame = tk.Frame(win, bg=APP_BG)
        v_frame.pack(pady=5)
        for vt in self.vehicle_types:
            tk.Radiobutton(
                v_frame,
                text=vt,
                variable=v_type,
                value=vt,
                bg=APP_BG,
                fg=TEXT_COLOR,
                selectcolor=PANEL_BG,
                activebackground=APP_BG,
                activeforeground=TEXT_COLOR,
            ).pack(side="left", padx=5)

        tk.Label(win, text="Block:", bg=APP_BG, fg=TEXT_COLOR, font=("Arial", 10)).pack(pady=3)
        block_entry = tk.Entry(win, width=18)
        self.style_entry(block_entry)
        block_entry.pack()
        block_entry.focus_set()

        tk.Label(win, text="Row (1 or 2):", bg=APP_BG, fg=TEXT_COLOR, font=("Arial", 10)).pack(pady=3)
        row_entry = tk.Entry(win, width=18)
        self.style_entry(row_entry)
        row_entry.pack()

        tk.Label(win, text="Column:", bg=APP_BG, fg=TEXT_COLOR, font=("Arial", 10)).pack(pady=3)
        col_entry = tk.Entry(win, width=18)
        self.style_entry(col_entry)
        col_entry.pack()

        def focus_next_widget(event):
            event.widget.tk_focusNext().focus()
            return "break"

        def free_spot(event=None):
            vehicle = v_type.get()
            block = block_entry.get().strip().upper()

            if block not in self.parking_status[vehicle]:
                messagebox.showerror("Error", f"Invalid block '{block}' for {vehicle}!")
                return

            try:
                row = int(row_entry.get())
                col = int(col_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Row/Column must be valid numbers!")
                return

            max_rows = self.parking_data[vehicle]["blocks"][block]["rows"]
            max_cols = self.parking_data[vehicle]["blocks"][block]["cols"]

            if row < 1 or row > max_rows:
                messagebox.showerror("Error", f"Row must be between 1 and {max_rows}!")
                return

            if col < 1 or col > max_cols:
                messagebox.showerror("Error", f"Column must be between 1 and {max_cols}!")
                return

            key = f"R{row}C{col}"
            status = self.parking_status[vehicle][block]["occupied"]
            details = self.spot_details[vehicle][block].get(key)

            if key not in status or not details:
                messagebox.showerror("Error", f"Spot {key} in Block {block} is already free.")
                return

            duration_seconds = time.time() - details["entry_timestamp"]
            duration_hours = max(1, math.ceil(duration_seconds / 3600))
            extra_hours = max(0, duration_hours - BASE_PARKING_HOURS)
            amount = BASE_PARKING_AMOUNT + (extra_hours * PARKING_RATE_PER_HOUR)
            exit_dt = datetime.now()

            status.remove(key)
            self.spot_details[vehicle][block].pop(key, None)
            self.update_exit_in_db(details["ticket_number"], exit_dt, amount)

            self.create_summary_table()
            if self.current_vehicle.get() == vehicle:
                self.show_block_detail(block)

            win.destroy()
            self.send_departure_to_whatsapp(
                vehicle=vehicle,
                block=block,
                key=key,
                vehicle_number=details["vehicle_number"],
                phone_number=details["phone_number"],
                ticket_number=details["ticket_number"],
                entry_dt=details["entry_datetime"],
                exit_dt=exit_dt,
                hours=duration_hours,
                amount=amount,
            )
            self.show_departure_slip(
                vehicle=vehicle,
                block=block,
                key=key,
                hours=duration_hours,
                amount=amount,
                ticket_number=details["ticket_number"],
                vehicle_number=details["vehicle_number"],
                phone_number=details["phone_number"],
                entry_dt=details["entry_datetime"],
                exit_dt=exit_dt,
            )

        block_entry.bind("<Return>", focus_next_widget)
        row_entry.bind("<Return>", focus_next_widget)
        col_entry.bind("<Return>", lambda event: free_spot())

        tk.Button(
            win,
            text="Process Departure",
            bg=ACCENT_GREEN,
            fg="white",
            font=("Arial", 11, "bold"),
            command=free_spot,
        ).pack(pady=20)

        win.wait_window(win)

    def show_departure_slip(self, vehicle, block, key, hours, amount, ticket_number, vehicle_number, phone_number, entry_dt, exit_dt):
        win = tk.Toplevel(self.root)
        win.title("Departure Slip & Payment")
        win.configure(bg=CARD_BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self.center_popup(win, 520, 700)

        tk.Label(
            win,
            text="Spot Freed & Ready for Payment",
            font=("Arial", 13, "bold"),
            fg=TITLE_COLOR,
            bg=CARD_BG,
        ).pack(pady=10)

        info_frame = tk.Frame(win, bg=PANEL_BG, padx=10, pady=10, borderwidth=1, relief="solid")
        info_frame.pack(pady=5, padx=20, fill="x")

        tk.Label(info_frame, text=f"Ticket No: {ticket_number}", font=("Arial", 11, "bold"), bg=PANEL_BG, fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(info_frame, text=f"Vehicle No: {vehicle_number}", font=("Arial", 11), bg=PANEL_BG, fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(info_frame, text=f"Phone No: {phone_number}", font=("Arial", 11), bg=PANEL_BG, fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(info_frame, text=f"Vehicle Type: {vehicle}", font=("Arial", 11), bg=PANEL_BG, fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(info_frame, text=f"Block/Spot: {block}/{key}", font=("Arial", 11), bg=PANEL_BG, fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(
            info_frame,
            text=f"Entry Time: {entry_dt.strftime('%d-%m-%Y %I:%M:%S %p')}",
            font=("Arial", 11),
            bg=PANEL_BG,
            fg=TEXT_COLOR,
        ).pack(anchor="w")
        tk.Label(
            info_frame,
            text=f"Exit Time: {exit_dt.strftime('%d-%m-%Y %I:%M:%S %p')}",
            font=("Arial", 11),
            bg=PANEL_BG,
            fg=TEXT_COLOR,
        ).pack(anchor="w")
        tk.Label(info_frame, text=f"Duration: {hours} hours", font=("Arial", 11), bg=PANEL_BG, fg=TEXT_COLOR).pack(anchor="w")

        tk.Label(
            win,
            text=f"Total Amount Due: Rs. {amount}",
            font=("Arial", 16, "bold"),
            fg=WARNING_COLOR,
            bg=CARD_BG,
        ).pack(pady=10)

        qr_data = f"upi://pay?pa={UPI_ID}&am={amount}.00&cu=INR&pn=SmartParking"
        try:
            qr_img = qrcode.make(qr_data)
            qr_img = qr_img.resize((200, 200), Image.Resampling.LANCZOS)
            qr_img_tk = ImageTk.PhotoImage(qr_img)
            tk.Label(win, image=qr_img_tk, bg=CARD_BG).pack(pady=10)
            win.qr_img = qr_img_tk
        except Exception as err:
            tk.Label(
                win,
                text="QR Code generation failed. Please check console for details.",
                fg="red",
                bg=CARD_BG,
            ).pack()
            print(f"QR Error: {err}")

        button_frame = tk.Frame(win, bg=CARD_BG)
        button_frame.pack(pady=15)

        tk.Button(
            button_frame,
            text="Payment Done (Close)",
            bg=ACCENT_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            command=win.destroy,
        ).pack(side="left", padx=6)

        win.wait_window(win)

    def on_close(self):
        if self.db_connection and self.db_connection.is_connected():
            self.db_connection.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartParking(root)
    if not MYSQL_CONNECTOR_AVAILABLE:
        messagebox.showwarning(
            "Dependency Warning",
            "MySQL connector is not installed.\n"
            "Install it with: pip install mysql-connector-python\n"
            "The app will run, but database insert/update will not happen.",
        )
    elif not app.db_connection:
        messagebox.showwarning(
            "Database Warning",
            "MySQL connection failed. The app will run, but database insert/update will not happen.\n"
            "Please check MYSQL_CONFIG values.",
        )
    root.mainloop()
