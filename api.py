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

def setup_database():
    """Calls the C++ executable to initialize the database."""
    logging.info("Checking for database...")
    if not os.path.exists('resource_matching.db'):
        logging.info("Database not found. Initializing...")
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
        logging.info("Database already exists.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ResourceMatcherHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        """Handles GET requests for fetching data."""
        try:
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)

            if parsed_path.path == '/projects':
                self.get_projects()
            elif parsed_path.path == '/skills':
                self.get_skills()
            elif parsed_path.path == '/resource_assignments':
                self.get_resource_assignments()
            elif parsed_path.path == '/match_resources' and 'project_id' in query_params:
                project_id = int(query_params['project_id'][0])
                self.get_potential_matches(project_id) # New handler
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in do_GET: {e}")
            self.send_error(500, "Internal Server Error")

    def do_POST(self):
        """Handles POST requests for creating new tasks."""
        try:
            parsed_path = urlparse(self.path)
            if parsed_path.path == '/tasks':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                task_details = json.loads(post_data)
                self.allocate_new_task(task_details)
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in do_POST: {e}")
            self.send_error(500, "Internal Server Error")

    def get_skills(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT skill FROM Resource_Skills ORDER BY skill")
        skills = [s[0] for s in cursor.fetchall()]
        conn.close()
        self._send_json_response(skills)

    def allocate_new_task(self, details):
        """Calls the C++ executable to allocate a new task based on new logic."""
        logging.info(f"Calling C++ allocator for task: {details['task_name']}")
        try:
            args = [
                MATCHER_EXEC,
                "--allocate",
                details['project_name'],
                details['task_name'],
                details['skill'],
                str(details['duration_hours'])
            ]
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ allocator returned an error: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")
        except Exception as e:
            logging.error(f"Error during allocation: {e}")
            self.send_error(500, "Internal Server Error")

    def do_DELETE(self):
        """Handles DELETE requests for completing tasks."""
        try:
            # Use regex to find a path like /tasks/123
            match = re.match(r'/tasks/(\d+)', self.path)
            if match:
                task_id = int(match.group(1))
                self.complete_task(task_id)
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in do_DELETE: {e}")
            self.send_error(500, "Internal Server Error")

    def complete_task(self, task_id):
        """Calls the C++ backend to mark a task as complete."""
        logging.info(f"Calling C++ backend to complete task_id: {task_id}")
        try:
            args = [MATCHER_EXEC, "--complete", str(task_id)]
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ complete task returned an error: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")

    def get_resource_assignments(self):
        """Fetches assignments and now includes the task_id."""
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        query = """
            SELECT
                R.resource_name,
                T.task_id, -- Added this
                T.task_name,
                P.project_name,
                T.duration_hours,
                T.schedule_from,
                T.schedule_to
            FROM Assignments A
            JOIN Resources R ON A.resource_id = R.resource_id
            JOIN Tasks T ON A.task_id = T.task_id
            JOIN Projects P ON T.project_id = P.project_id
            ORDER BY R.resource_name, T.schedule_from;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        assignments = {}
        for row in rows:
            resource_name, task_id, task_name, project_name, duration, start, end = row
            if resource_name not in assignments:
                assignments[resource_name] = {"resource_name": resource_name, "assigned_tasks": []}
            assignments[resource_name]["assigned_tasks"].append({
                "task_id": task_id, # Now included in the response
                "task_name": task_name,
                "project_name": project_name,
                "duration_hours": duration,
                "schedule_from": start,
                "schedule_to": end
            })
        self._send_json_response(list(assignments.values()))

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
