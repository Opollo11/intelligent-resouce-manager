import http.server
import socketserver
import json
import sqlite3
import subprocess
from urllib.parse import urlparse, parse_qs
import logging
import os
from collections import defaultdict

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
            logging.error("The C++ executable failed during database setup.")
            logging.error(f"Stderr: {e.stderr}")
            exit(1)
    else:
        logging.info("Database already exists.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ResourceMatcherHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)

            if parsed_path.path == '/projects':
                self.get_projects()
            elif parsed_path.path == '/match_resources' and 'project_id' in query_params:
                project_id = int(query_params['project_id'][0])
                self.get_matched_resources(project_id)
            elif parsed_path.path == '/resource_assignments':
                self.get_resource_assignments()
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            logging.error(f"An error occurred in the Python handler: {e}")
            self.send_error(500, "Internal Server Error")

    def get_projects(self):
        """Fetches project list; this simple query can remain in Python."""
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, project_name FROM Projects")
        projects = cursor.fetchall()
        conn.close()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps([{'id': p[0], 'name': p[1]} for p in projects]).encode())

    def get_matched_resources(self, project_id):
        """Calls the C++ executable to get matching resources."""
        logging.info(f"Calling C++ matcher for project_id: {project_id}")
        try:
            result = subprocess.run(
                [MATCHER_EXEC, str(project_id)],
                capture_output=True, text=True, check=True
            )
            json_output = result.stdout
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json_output.encode('utf-8'))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ matcher returned an error for project_id {project_id}.")
            logging.error(f"Stderr: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")
        except FileNotFoundError:
            logging.error(f"The C++ executable '{MATCHER_EXEC}' was not found.")
            self.send_error(500, "Matcher executable not found")

    def get_resource_assignments(self):
        """Fetches detailed task assignments for each resource."""
        logging.info("Fetching resource assignment data.")
        try:
            conn = sqlite3.connect('resource_matching.db')
            cursor = conn.cursor()
            query = """
                SELECT
                    R.resource_id,
                    R.resource_name,
                    T.task_name,
                    P.project_name
                FROM
                    Resources R
                JOIN
                    Resource_Skills RS ON R.resource_id = RS.resource_id
                JOIN
                    Tasks T ON RS.skill = T.required_skill
                JOIN
                    Projects P ON T.project_id = P.project_id
                JOIN
                    Resource_Availability RA ON R.resource_id = RA.resource_id
                WHERE
                    RA.available_from <= T.schedule_from AND RA.available_to >= T.schedule_to
                ORDER BY
                    R.resource_name, P.project_name, T.task_name;
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            assignments = {}
            for row in rows:
                resource_id, resource_name, task_name, project_name = row
                if resource_id not in assignments:
                    assignments[resource_id] = {
                        "resource_id": resource_id,
                        "resource_name": resource_name,
                        "assigned_tasks": []
                    }
                assignments[resource_id]["assigned_tasks"].append({
                    "task_name": task_name,
                    "project_name": project_name
                })

            assignments_list = list(assignments.values())

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(assignments_list).encode('utf-8'))

        except sqlite3.Error as e:
            logging.error(f"Database error while fetching assignments: {e}")
            self.send_error(500, "Database error")

# --- Server Execution ---
if __name__ == "__main__":
    setup_database()
    PORT = 8000
    with socketserver.TCPServer(("", PORT), ResourceMatcherHandler) as httpd:
        logging.info(f"Python API server starting on port {PORT}")
        httpd.serve_forever()
