#include <iostream>
#include <string>
#include <vector>
#include <stdexcept>
#include <limits>
#include "sqlite3.h"
#include "json.hpp"
#include <chrono>
#include <sstream>
#include <iomanip>

using json = nlohmann::json;

// Helper to format a time_point to a date string (YYYY-MM-DD)
std::string format_date(const std::chrono::system_clock::time_point& time_point) {
    std::time_t time = std::chrono::system_clock::to_time_t(time_point);
    std::tm tm = *std::localtime(&time);
    std::stringstream ss;
    ss << std::put_time(&tm, "%Y-%m-%d");
    return ss.str();
}

// Helper function to execute SQL statements
void execute_sql(sqlite3* db, const char* sql) {
    char* err_msg = 0;
    int rc = sqlite3_exec(db, sql, 0, 0, &err_msg);
    if (rc != SQLITE_OK) {
        std::string error = "SQL error: " + std::string(err_msg);
        sqlite3_free(err_msg);
        throw std::runtime_error(error);
    }
}

// Updated to include Resource_Availability table again
void setup_database() {
    sqlite3* db;
    if (sqlite3_open("resource_matching.db", &db)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    execute_sql(db, "DROP TABLE IF EXISTS Projects;");
    execute_sql(db, "DROP TABLE IF EXISTS Tasks;");
    execute_sql(db, "DROP TABLE IF EXISTS Resources;");
    execute_sql(db, "DROP TABLE IF EXISTS Resource_Skills;");
    execute_sql(db, "DROP TABLE IF EXISTS Resource_Availability;"); // Re-added
    execute_sql(db, "DROP TABLE IF EXISTS Assignments;");
    
    execute_sql(db, "CREATE TABLE Projects (project_id INTEGER PRIMARY KEY AUTOINCREMENT, project_name TEXT UNIQUE);");
    execute_sql(db, "CREATE TABLE Tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, task_name TEXT, required_skill TEXT, duration_hours INTEGER, schedule_from TEXT, schedule_to TEXT);");
    execute_sql(db, "CREATE TABLE Resources (resource_id INTEGER PRIMARY KEY, resource_name TEXT);");
    execute_sql(db, "CREATE TABLE Resource_Skills (resource_id INTEGER, skill TEXT);");
    execute_sql(db, "CREATE TABLE Resource_Availability (availability_id INTEGER PRIMARY KEY, resource_id INTEGER, available_from TEXT, available_to TEXT);"); // Re-added
    execute_sql(db, "CREATE TABLE Assignments (assignment_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, resource_id INTEGER);");

    execute_sql(db, "BEGIN TRANSACTION;");
    execute_sql(db, "INSERT INTO Projects (project_name) VALUES ('E-commerce Website'), ('Mobile Banking App');");
    execute_sql(db, "INSERT INTO Tasks (project_id, task_name, required_skill, duration_hours, schedule_from, schedule_to) VALUES (1, 'Setup Database', 'SQL', 40, '2025-07-29', '2025-08-03'), (2, 'Design Database Schema', 'Mongo DB', 24, '2025-07-29', '2025-08-01');");
    execute_sql(db, "INSERT INTO Resources VALUES (101, 'Ram'), (102, 'Shyam'), (103, 'Kiran'), (104, 'Dhina');");
    execute_sql(db, "INSERT INTO Resource_Skills VALUES (101, 'SQL'), (101, 'C#'), (102, 'C#'), (102, 'Web Services/Rest API'), (103, 'Mongo DB'), (103, 'Node.JS'), (104, 'SQL'), (104, 'Node.JS');");
    execute_sql(db, "INSERT INTO Resource_Availability VALUES (1, 101, '2025-07-01', '2025-08-30'), (2, 102, '2025-07-15', '2025-09-15'), (3, 103, '2025-07-01', '2025-12-31'), (4, 104, '2025-08-01', '2025-08-15');");
    execute_sql(db, "INSERT INTO Assignments (task_id, resource_id) VALUES (1, 101), (2, 103);");
    execute_sql(db, "COMMIT;");

    sqlite3_close(db);
}

// Function to find potential matches for a project's tasks
void find_matches(int project_id) {
    sqlite3* db;
    sqlite3_stmt* stmt;
    json results = json::array();

    if (sqlite3_open_v2("resource_matching.db", &db, SQLITE_OPEN_READONLY, NULL)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    // Get all tasks for the project
    sqlite3_prepare_v2(db, "SELECT task_name, required_skill, schedule_from, schedule_to FROM Tasks WHERE project_id = ?;", -1, &stmt, 0);
    sqlite3_bind_int(stmt, 1, project_id);

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        json task_result;
        task_result["task_name"] = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        std::string required_skill = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        std::string schedule_from = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
        std::string schedule_to = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        
        task_result["required_skill"] = required_skill;
        task_result["schedule"] = schedule_from + " to " + schedule_to;

        // Find all resources who have the skill and whose general availability overlaps the task schedule
        sqlite3_stmt* resource_stmt;
        const char* resources_sql = "SELECT R.resource_id, R.resource_name FROM Resources R JOIN Resource_Skills RS ON R.resource_id = RS.resource_id JOIN Resource_Availability RA ON R.resource_id = RA.resource_id WHERE RS.skill = ? AND RA.available_to >= ? AND RA.available_from <= ?;";
        sqlite3_prepare_v2(db, resources_sql, -1, &resource_stmt, 0);
        sqlite3_bind_text(resource_stmt, 1, required_skill.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(resource_stmt, 2, schedule_from.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(resource_stmt, 3, schedule_to.c_str(), -1, SQLITE_STATIC);

        json matched_resources = json::array();
        while (sqlite3_step(resource_stmt) == SQLITE_ROW) {
            json resource;
            resource["id"] = sqlite3_column_int(resource_stmt, 0);
            resource["name"] = reinterpret_cast<const char*>(sqlite3_column_text(resource_stmt, 1));
            matched_resources.push_back(resource);
        }
        sqlite3_finalize(resource_stmt);
        task_result["matched_resources"] = matched_resources;
        results.push_back(task_result);
    }
    sqlite3_finalize(stmt);
    sqlite3_close(db);
    std::cout << results.dump(4) << std::endl;
}

// Function to allocate a new task
void allocate_task(const std::string& project_name, const std::string& task_name, const std::string& skill, int duration_hours) {
    // This function's logic remains the same as v3
    // ... (logic from previous version)
}

// Main function now handles three modes
int main(int argc, char* argv[]) {
    try {
        if (argc < 2) {
            std::cerr << "Usage: " << argv[0] << " <project_id> | --init | --allocate ..." << std::endl;
            return 1;
        }

        std::string mode = argv[1];
        if (mode == "--init") {
            setup_database();
            std::cout << "Database initialized successfully." << std::endl;
        } else if (mode == "--allocate") {
            if (argc != 6) {
                std::cerr << "Usage for --allocate: <project_name> <task_name> <skill> <duration_hours>" << std::endl;
                return 1;
            }
            allocate_task(argv[2], argv[3], argv[4], std::stoi(argv[5]));
        } else {
            // Default mode: find potential matches for a given project ID
            find_matches(std::stoi(mode));
        }
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
