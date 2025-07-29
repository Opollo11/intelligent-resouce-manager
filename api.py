import http.server
import socketserver
import json
import sqlite3
import subprocess
from urllib.parse import urlparse, parse_qs
import logging
import os

MATCHER_EXEC = "./matcher"

def setup_database():
    # This function remains the same
    # ...
    pass # Placeholder for brevity

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
        # This function remains the same
        # ...
        pass # Placeholder for brevity

    def get_projects(self):
        conn = sqlite3.connect('resource_matching.db')
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, project_name FROM Projects")
        projects = [{'id': p[0], 'name': p[1]} for p in cursor.fetchall()]
        conn.close()
        self._send_json_response(projects)

    def get_skills(self):
        # This function remains the same
        # ...
        pass # Placeholder for brevity

    def get_potential_matches(self, project_id):
        """Calls C++ backend to find all potential matches for a project's tasks."""
        logging.info(f"Calling C++ matcher for potential matches for project_id: {project_id}")
        try:
            # Note the different arguments sent to the C++ executable
            result = subprocess.run([MATCHER_EXEC, str(project_id)], capture_output=True, text=True, check=True)
            self._send_json_response(json.loads(result.stdout))
        except subprocess.CalledProcessError as e:
            logging.error(f"C++ matcher returned an error: {e.stderr}")
            self.send_error(500, "Error in C++ backend processing")

    def allocate_new_task(self, details):
        # This function remains the same
        # ...
        pass # Placeholder for brevity

    def get_resource_assignments(self):
        # This function remains the same
        # ...
        pass # Placeholder for brevity

    def _send_json_response(self, data, status=200):
        # This helper function remains the same
        # ...
        pass # Placeholder for brevity

if __name__ == "__main__":
    setup_database()
    PORT = 8000
    with socketserver.TCPServer(("", PORT), ResourceMatcherHandler) as httpd:
        logging.info(f"Python API server starting on port {PORT}")
        httpd.serve_forever()
