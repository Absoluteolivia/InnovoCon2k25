import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
import threading
import sqlite3
from plyer import notification
import webbrowser
from datetime import datetime, timedelta
from tkcalendar import DateEntry
import os
from googleapiclient.discovery import build

# Configuration
DB_FILE = "reminders.db"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "your_api_key_here")  # Replace with your API key

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine TEXT NOT NULL,
            reminder_datetime TEXT NOT NULL,
            frequency TEXT NOT NULL,
            status TEXT DEFAULT 'Pending'
        )
    ''')
    
    cursor.execute("PRAGMA table_info(reminders)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'frequency' not in columns:
        cursor.execute('''
            ALTER TABLE reminders ADD COLUMN frequency TEXT NOT NULL DEFAULT 'Once'
        ''')
    
    conn.commit()
    conn.close()

class MedicineReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Medicine Reminder")
        self.root.geometry("800x600")
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.setup_ui()
        self.load_reminders()
        self.check_pending_reminders()
        self.running_reminders = set()
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Input Section
        input_frame = ttk.LabelFrame(main_frame, text="Set New Reminder", padding=10)
        input_frame.grid(row=0, column=0, sticky="ew", pady=5)
        
        ttk.Label(input_frame, text="Medicine Name:").grid(row=0, column=0, sticky="w")
        self.medicine_entry = ttk.Entry(input_frame, width=30)
        self.medicine_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(input_frame, text="Date:").grid(row=1, column=0, sticky="w")
        self.date_entry = DateEntry(input_frame, date_pattern="yyyy-mm-dd")
        self.date_entry.grid(row=1, column=1, padx=5, sticky="w")
        
        ttk.Label(input_frame, text="Time (HH:MM):").grid(row=2, column=0, sticky="w")
        self.time_entry = ttk.Entry(input_frame, width=8)
        self.time_entry.grid(row=2, column=1, padx=5, sticky="w")
        
        ttk.Label(input_frame, text="Frequency:").grid(row=3, column=0, sticky="w")
        self.frequency_combo = ttk.Combobox(input_frame, values=["Once", "Daily", "Weekly"])
        self.frequency_combo.grid(row=3, column=1, padx=5, sticky="w")
        self.frequency_combo.current(0)
        
        ttk.Button(input_frame, text="Set Reminder", command=self.set_reminder)\
           .grid(row=4, column=1, pady=5, sticky="e")

        # Reminders List
        list_frame = ttk.LabelFrame(main_frame, text="Upcoming Reminders", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        
        columns = ("id", "medicine", "datetime", "frequency", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("medicine", text="Medicine")
        self.tree.heading("datetime", text="Date & Time")
        self.tree.heading("frequency", text="Frequency")
        self.tree.heading("status", text="Status")
        self.tree.column("id", width=0, stretch=tk.NO)
        self.tree.column("medicine", width=150)
        self.tree.column("datetime", width=150)
        self.tree.column("frequency", width=100, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Action Buttons
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(pady=5)
        
        ttk.Button(button_frame, text="Mark as Taken", command=self.mark_as_taken)\
           .grid(row=0, column=0, padx=2)
        ttk.Button(button_frame, text="Snooze", command=self.snooze_reminder)\
           .grid(row=0, column=1, padx=2)
        ttk.Button(button_frame, text="Delete", command=self.delete_reminder)\
           .grid(row=0, column=2, padx=2)
        ttk.Button(button_frame, text="YouTube Info", command=self.show_youtube_info)\
           .grid(row=0, column=3, padx=2)
        ttk.Button(button_frame, text="Save Report", command=self.save_report)\
           .grid(row=0, column=4, padx=2)
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
    
    def validate_time(self, time_str):
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False
    
    def set_reminder(self):
        medicine = self.medicine_entry.get()
        date = self.date_entry.get_date()
        time_str = self.time_entry.get()
        frequency = self.frequency_combo.get()
        
        if not all([medicine, date, time_str, frequency]):
            messagebox.showerror("Error", "All fields are required!")
            return
        
        if not self.validate_time(time_str):
            messagebox.showerror("Error", "Invalid time format! Use HH:MM")
            return
        
        reminder_datetime = f"{date} {time_str}"
        if datetime.fromisoformat(reminder_datetime) < datetime.now():
            messagebox.showerror("Error", "Cannot set reminder for past time!")
            return
        
        reminder_id = self.save_reminder(medicine, reminder_datetime, frequency)
        self.schedule_notification(reminder_id, medicine, reminder_datetime, frequency)
        
        messagebox.showinfo("Success", f"Reminder set for {medicine} at {reminder_datetime}")
        self.medicine_entry.delete(0, tk.END)
        self.time_entry.delete(0, tk.END)
    
    def save_reminder(self, medicine, reminder_datetime, frequency):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reminders (medicine, reminder_datetime, frequency) 
                VALUES (?, ?, ?)
            ''', (medicine, reminder_datetime, frequency))
            reminder_id = cursor.lastrowid
            conn.commit()
            return reminder_id
        finally:
            conn.close()
    
    def load_reminders(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, medicine, reminder_datetime, frequency, status 
                FROM reminders 
                ORDER BY reminder_datetime
            ''')
            for row in cursor.fetchall():
                self.tree.insert("", tk.END, values=row)
        finally:
            conn.close()
    
    def get_selected_reminder(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a reminder!")
            return None
        return self.tree.item(selection[0])['values']
    
    def mark_as_taken(self):
        if reminder := self.get_selected_reminder():
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('UPDATE reminders SET status = "Taken" WHERE id = ?', (reminder[0],))
                conn.commit()
            finally:
                conn.close()
            self.load_reminders()
    
    def snooze_reminder(self):
        if not (reminder := self.get_selected_reminder()):
            return
        
        new_time = datetime.fromisoformat(reminder[2]) + timedelta(minutes=5)
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE reminders 
                SET reminder_datetime = ?, status = 'Snoozed'
                WHERE id = ?
            ''', (new_time.isoformat(), reminder[0]))
            conn.commit()
        finally:
            conn.close()
        self.load_reminders()
        messagebox.showinfo("Snoozed", f"New reminder time: {new_time.strftime('%Y-%m-%d %H:%M')}")
    
    def delete_reminder(self):
        if reminder := self.get_selected_reminder():
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder[0],))
                conn.commit()
            finally:
                conn.close()
            self.load_reminders()
    
    def show_youtube_info(self):
        if not (reminder := self.get_selected_reminder()):
            return
        
        try:
            youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
            response = youtube.search().list(
                q=f"{reminder[1]} medicine information",
                part="snippet",
                type="video",
                maxResults=1
            ).execute()
            
            if response["items"]:
                video_id = response["items"][0]["id"]["videoId"]
                webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")
            else:
                messagebox.showinfo("Info", "No relevant videos found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch YouTube info: {str(e)}")
    
    def schedule_notification(self, reminder_id, medicine, reminder_datetime, frequency):
        def notification_worker():
            nonlocal reminder_id
            target_time = datetime.fromisoformat(reminder_datetime)
            
            while True:
                now = datetime.now()
                if now >= target_time:
                    with sqlite3.connect(DB_FILE) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT status FROM reminders WHERE id = ?', (reminder_id,))
                        if (status := cursor.fetchone()[0]) == 'Pending':
                            self.root.after(0, lambda: self.show_notification(reminder_id))
                            
                            if frequency in ["Daily", "Weekly"]:
                                delta = timedelta(days=1) if frequency == "Daily" else timedelta(weeks=1)
                                new_datetime = (target_time + delta).isoformat()
                                new_id = self.save_reminder(medicine, new_datetime, frequency)
                                self.schedule_notification(new_id, medicine, new_datetime, frequency)
                    break
                time.sleep(30)
        
        threading.Thread(target=notification_worker, daemon=True).start()
    
    def show_notification(self, reminder_id):
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT medicine FROM reminders WHERE id = ?', (reminder_id,))
            medicine = cursor.fetchone()[0]
        
        notification.notify(
            title="Medicine Reminder",
            message=f"Time to take your {medicine}!",
            timeout=10
        )
        self.root.after(0, lambda: self.handle_notification_response(reminder_id))
    
    def handle_notification_response(self, reminder_id):
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT medicine FROM reminders WHERE id = ?', (reminder_id,))
            medicine = cursor.fetchone()[0]
        
        response = messagebox.askyesno("Confirmation", f"Did you take {medicine}?", icon="question")
        
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE reminders 
                    SET status = ? 
                    WHERE id = ?
                ''', ('Taken' if response else 'Missed', reminder_id))
                conn.commit()
        finally:
            self.load_reminders()
    
    def check_pending_reminders(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE reminders 
                SET status = 'Missed' 
                WHERE reminder_datetime < ? 
                AND status = 'Pending'
            ''', (now,))
            conn.commit()
        finally:
            conn.close()
        self.load_reminders()

    def save_report(self):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT medicine, reminder_datetime, status FROM reminders')
                reminders = cursor.fetchall()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", str(e))
            return

        if not reminders:
            messagebox.showinfo("Info", "No reminders found.")
            return

        report = "Medicine Reminder Report\n\n"
        report += f"{'Medicine':<20}{'Date & Time':<25}{'Status':<10}\n"
        report += "-" * 55 + "\n"
        for med, dt, status in reminders:
            report += f"{med:<20}{dt:<25}{status:<10}\n"

        if path := filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        ):
            try:
                with open(path, 'w') as f:
                    f.write(report)
                messagebox.showinfo("Success", "Report saved successfully!")
            except IOError as e:
                messagebox.showerror("Error", f"Failed to save report: {e}")

if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = MedicineReminderApp(root)
    root.mainloop()