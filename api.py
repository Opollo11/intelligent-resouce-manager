import http.server
import socketserver
import json
import sqlite3
import subprocess
from urllib.parse import urlparse, parse_qs
import logging
import os
import re

MATCHER_EXEC = "./matcher"

def db_is_initialized():
    """Checks if the database is properly initialized by looking for the Projects table."""
    if not os.path.exists('resource_matching.db'):
        return False
    try:
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Projects';")
        if cursor.fetchone() is None:
            conn.close()
            return False
        conn.close()
        return True
    except sqlite3.Error:
        return False

def setup_database():
    """Initializes the database if it's not already set up properly."""
    logging.info("Checking database initialization status...")
    if not db_is_initialized():
        logging.info("Database not initialized or is empty. Running setup...")
        if os.path.exists('resource_matching.db'):
            try:
                os.remove('resource_matching.db')
                logging.info("Removed stale database file.")
            except OSError as e:
                logging.error(f"Error removing database file: {e}")
                exit(1)
        
        try:
            subprocess.run([MATCHER_EXEC, "--init"], check=True, capture_output=True, text=True)
            logging.info("Database initialized successfully by C++ executable.")
        except FileNotFoundError:
            logging.error(f"FATAL: The C++ executable '{MATCHER_EXEC}' was not found.")
            logging.error("Please compile it first (e.g., using compile.sh).")
            exit(1)
        except subprocess.CalledProcessError as e:
            logging.error(f"The C++ executable failed during database setup: {e.stderr}")
            exit(1)
    else:
        logging.info("Database is already initialized.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ResourceMatcherHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)

            if parsed_path.path == '/projects':
                self.get_projects()
            elif parsed_path.path == '/skills':
                self.get_skills()
            elif parsed_path.path == '/resources':
                self.get_resources()
            elif parsed_path.path == '/resource_assignments':
                self.get_resource_assignments()
            elif parsed_path.path == '/completed_tasks':
                self.get_completed_tasks()
            elif parsed_path.path == '/match_resources' and 'project_id' in query_params:
                project_id = int(query_params['project_id'][0])
                self.get_potential_matches(project_id)
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in do_GET: {e}")
            self.send_error(500, "Internal Server Error")

    def do_POST(self):
        try:
            parsed_path = urlparse(self.path)
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            details = json.loads(post_data)

            if parsed_path.path == '/tasks':
                self.allocate_new_task(details)
            elif parsed_path.path == '/resources':
                self.add_new_resource(details)
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in do_POST: {e}")
            self.send_error(500, "Internal Server Error")
        
    def do_DELETE(self):
        try:
            match = re.match(r'/tasks/(\d+)', self.path)
            if match:
                task_id = int(match.group(1))
                self.complete_task(task_id)
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in do_DELETE: {e}")
            self.send_error(500, "Internal Server Error")

    def get_projects(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, project_name FROM Projects")
        projects = [{'id': p[0], 'name': p[1]} for p in cursor.fetchall()]
        conn.close()
        self._send_json_response(projects)
        
    def get_potential_matches(self, project_id):
        logging.info(f"Calling C++ matcher for potential matches for project_id: {project_id}")
        try:
            result = subprocess.run([MATCHER_EXEC, str(project_id)], capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ matcher returned an error: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")

    def get_skills(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT skill FROM Resource_Skills ORDER BY skill")
        skills = [s[0] for s in cursor.fetchall()]
        conn.close()
        self._send_json_response(skills)

    def get_resources(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT resource_id, resource_name FROM Resources ORDER BY resource_name")
        resources = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]
        conn.close()
        self._send_json_response(resources)

    def allocate_new_task(self, details):
        logging.info(f"Calling C++ allocator for task: {details['task_name']}")
        try:
            args = [MATCHER_EXEC, "--allocate", details['project_name'], details['task_name'], details['skill'], str(details['duration_hours'])]
            if 'resource_id' in details and details['resource_id'] is not None:
                args.append(str(details['resource_id']))
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except Exception as e:
            logging.error(f"Error during allocation: {e}")
            self.send_error(500, "Internal Server Error")

    def add_new_resource(self, details):
        name = details.get("name")
        skills = details.get("skills", [])
        if not name or not skills:
            self.send_error(400, "Name and skills are required.")
            return
        logging.info(f"Calling C++ backend to add resource: {name}")
        try:
            args = [MATCHER_EXEC, "--add_resource", name]
            args.extend(skills)
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ add resource returned an error: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")

    def complete_task(self, task_id):
        logging.info(f"Calling C++ backend to complete task_id: {task_id}")
        try:
            args = [MATCHER_EXEC, "--complete", str(task_id)]
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ complete task returned an error: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")

    def get_resource_assignments(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        query = "SELECT R.resource_name, T.task_id, T.task_name, P.project_name, T.duration_hours, T.schedule_from, T.schedule_to FROM Assignments A JOIN Resources R ON A.resource_id = R.resource_id JOIN Tasks T ON A.task_id = T.task_id JOIN Projects P ON T.project_id = P.project_id ORDER BY R.resource_name, T.schedule_from;"
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        assignments = {}
        for row in rows:
            resource_name, task_id, task_name, project_name, duration, start, end = row
            if resource_name not in assignments:
                assignments[resource_name] = {"resource_name": resource_name, "assigned_tasks": []}
            assignments[resource_name]["assigned_tasks"].append({ "task_id": task_id, "task_name": task_name, "project_name": project_name, "duration_hours": duration, "schedule_from": start, "schedule_to": end })
        self._send_json_response(list(assignments.values()))

    def get_completed_tasks(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        query = "SELECT P.project_name, T.task_name, R.resource_name, T.completion_date FROM Tasks T JOIN Projects P ON T.project_id = P.project_id LEFT JOIN Resources R ON T.completed_by_resource_id = R.resource_id WHERE T.status = 'Completed' ORDER BY T.completion_date DESC;"
        cursor.execute(query)
        completed = [{"project_name": row[0], "task_name": row[1], "completed_by": row[2] if row[2] else "N/A", "completion_date": row[3]} for row in cursor.fetchall()]
        conn.close()
        self._send_json_response(completed)

    def _send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

if __name__ == "__main__":
    setup_database()
    PORT = 8000
    with socketserver.TCPServer(("", PORT), ResourceMatcherHandler) as httpd:
        logging.info(f"Python API server starting on port {PORT}")
        httpd.serve_forever()
