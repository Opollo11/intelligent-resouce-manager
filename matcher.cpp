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

//YYYY-MM-DD
std::string format_date(const std::chrono::system_clock::time_point& time_point) {
    std::time_t time = std::chrono::system_clock::to_time_t(time_point);
    std::tm tm = *std::localtime(&time);
    std::stringstream ss;
    ss << std::put_time(&tm, "%Y-%m-%d");
    return ss.str();
}

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
    execute_sql(db, "DROP TABLE IF EXISTS Resource_Availability;");
    execute_sql(db, "DROP TABLE IF EXISTS Assignments;");
    
    execute_sql(db, "CREATE TABLE Projects (project_id INTEGER PRIMARY KEY AUTOINCREMENT, project_name TEXT UNIQUE);");
    execute_sql(db, "CREATE TABLE Tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, task_name TEXT, required_skill TEXT, duration_hours INTEGER, schedule_from TEXT, schedule_to TEXT, status TEXT DEFAULT 'Pending', completed_by_resource_id INTEGER, completion_date TEXT);");
    execute_sql(db, "CREATE TABLE Resources (resource_id INTEGER PRIMARY KEY, resource_name TEXT);");
    execute_sql(db, "CREATE TABLE Resource_Skills (resource_id INTEGER, skill TEXT);");
    execute_sql(db, "CREATE TABLE Resource_Availability (availability_id INTEGER PRIMARY KEY, resource_id INTEGER, available_from TEXT, available_to TEXT);");
    execute_sql(db, "CREATE TABLE Assignments (assignment_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, resource_id INTEGER);");

    execute_sql(db, "BEGIN TRANSACTION;");
    execute_sql(db, "INSERT INTO Projects (project_name) VALUES ('E-commerce Website'), ('Mobile Banking App');");
    execute_sql(db, "INSERT INTO Tasks (project_id, task_name, required_skill, duration_hours, schedule_from, schedule_to, status) VALUES (1, 'Setup Database', 'SQL', 40, '2025-07-29', '2025-08-03', 'Assigned'), (2, 'Design Database Schema', 'Mongo DB', 24, '2025-07-29', '2025-08-01', 'Assigned');");
    execute_sql(db, "INSERT INTO Resources VALUES (101, 'Ram'), (102, 'Shyam'), (103, 'Kiran'), (104, 'Dhina');");
    execute_sql(db, "INSERT INTO Resource_Skills VALUES (101, 'SQL'), (101, 'C#'), (102, 'C#'), (102, 'Web Services/Rest API'), (103, 'Mongo DB'), (103, 'Node.JS'), (104, 'SQL'), (104, 'Node.JS');");
    execute_sql(db, "INSERT INTO Resource_Availability VALUES (1, 101, '2025-07-01', '2025-08-30'), (2, 102, '2025-07-15', '2025-09-15'), (3, 103, '2025-07-01', '2025-12-31'), (4, 104, '2025-08-01', '2025-08-15');");
    execute_sql(db, "INSERT INTO Assignments (task_id, resource_id) VALUES (1, 101), (2, 103);");
    execute_sql(db, "COMMIT;");

    sqlite3_close(db);
}

// find potential matches for tasks
void find_matches(int project_id) {
    sqlite3* db;
    sqlite3_stmt* stmt;
    json results = json::array();

    if (sqlite3_open_v2("resource_matching.db", &db, SQLITE_OPEN_READONLY, NULL)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    sqlite3_prepare_v2(db, "SELECT task_name, required_skill, schedule_from, schedule_to FROM Tasks WHERE project_id = ? AND status != 'Completed';", -1, &stmt, 0);
    sqlite3_bind_int(stmt, 1, project_id);

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        json task_result;
        task_result["task_name"] = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        std::string required_skill = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        std::string schedule_from = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
        std::string schedule_to = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        
        task_result["required_skill"] = required_skill;
        task_result["schedule"] = schedule_from + " to " + schedule_to;

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

void allocate_task(const std::string& project_name, const std::string& task_name, const std::string& skill, int duration_hours) {
    sqlite3* db;
    sqlite3_stmt* stmt;
    json result;

    if (sqlite3_open("resource_matching.db", &db)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    // Handle project: find or create
    long long project_id;
    sqlite3_prepare_v2(db, "SELECT project_id FROM Projects WHERE project_name = ?;", -1, &stmt, 0);
    sqlite3_bind_text(stmt, 1, project_name.c_str(), -1, SQLITE_STATIC);
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        project_id = sqlite3_column_int(stmt, 0);
    } else {
        sqlite3_finalize(stmt);
        sqlite3_prepare_v2(db, "INSERT INTO Projects (project_name) VALUES (?);", -1, &stmt, 0);
        sqlite3_bind_text(stmt, 1, project_name.c_str(), -1, SQLITE_STATIC);
        if (sqlite3_step(stmt) != SQLITE_DONE) throw std::runtime_error("Failed to create new project.");
        project_id = sqlite3_last_insert_rowid(db);
    }
    sqlite3_finalize(stmt);

    int best_resource_id = -1;
    std::string best_resource_name;
    std::string start_date_str;

    // Priority 1: Find a completely free resource
    const char* find_free_sql = "SELECT R.resource_id, R.resource_name FROM Resources R JOIN Resource_Skills RS ON R.resource_id = RS.resource_id WHERE RS.skill = ? AND R.resource_id NOT IN (SELECT DISTINCT resource_id FROM Assignments);";
    sqlite3_prepare_v2(db, find_free_sql, -1, &stmt, 0);
    sqlite3_bind_text(stmt, 1, skill.c_str(), -1, SQLITE_STATIC);
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        best_resource_id = sqlite3_column_int(stmt, 0);
        best_resource_name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        start_date_str = format_date(std::chrono::system_clock::now());
    }
    sqlite3_finalize(stmt);

    // Priority 2: Find resource with least work
    if (best_resource_id == -1) {
        const char* find_least_work_sql = R"(
            SELECT R.resource_id, R.resource_name, MAX(T.schedule_to), SUM(T.duration_hours) as total_hours
            FROM Resources R
            JOIN Resource_Skills RS ON R.resource_id = RS.resource_id
            LEFT JOIN Assignments A ON R.resource_id = A.resource_id
            LEFT JOIN Tasks T ON A.task_id = T.task_id
            WHERE RS.skill = ?
            GROUP BY R.resource_id
            ORDER BY total_hours ASC
            LIMIT 1;
        )";
        sqlite3_prepare_v2(db, find_least_work_sql, -1, &stmt, 0);
        sqlite3_bind_text(stmt, 1, skill.c_str(), -1, SQLITE_STATIC);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            best_resource_id = sqlite3_column_int(stmt, 0);
            best_resource_name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            // If resource->tasks? start after the last one: start now.
            const char* last_task_end = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            start_date_str = (last_task_end) ? std::string(last_task_end) : format_date(std::chrono::system_clock::now());
        }
        sqlite3_finalize(stmt);
    }

    if (best_resource_id != -1) {
        // Calculate end date
        std::chrono::system_clock::time_point start_tp = std::chrono::system_clock::now(); // Default to now
        std::tm tm = {};
        std::stringstream ss(start_date_str);
        ss >> std::get_time(&tm, "%Y-%m-%d");
        start_tp = std::chrono::system_clock::from_time_t(std::mktime(&tm));

        auto end_tp = start_tp + std::chrono::hours(duration_hours);
        std::string end_date_str = format_date(end_tp);

        // Insert new task
        sqlite3_prepare_v2(db, "INSERT INTO Tasks (project_id, task_name, required_skill, duration_hours, schedule_from, schedule_to) VALUES (?, ?, ?, ?, ?, ?);", -1, &stmt, 0);
        sqlite3_bind_int(stmt, 1, project_id);
        sqlite3_bind_text(stmt, 2, task_name.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 3, skill.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 4, duration_hours);
        sqlite3_bind_text(stmt, 5, start_date_str.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 6, end_date_str.c_str(), -1, SQLITE_STATIC);
        if (sqlite3_step(stmt) != SQLITE_DONE) throw std::runtime_error("Failed to insert new task.");
        sqlite3_finalize(stmt);
        
        long long last_task_id = sqlite3_last_insert_rowid(db);

        sqlite3_prepare_v2(db, "INSERT INTO Assignments (task_id, resource_id) VALUES (?, ?);", -1, &stmt, 0);
        sqlite3_bind_int(stmt, 1, last_task_id);
        sqlite3_bind_int(stmt, 2, best_resource_id);
        if (sqlite3_step(stmt) != SQLITE_DONE) throw std::runtime_error("Failed to insert new assignment.");
        sqlite3_finalize(stmt);

        result["success"] = true;
        result["message"] = "Task allocated successfully.";
        result["allocated_to"] = best_resource_name;
    } else {
        result["success"] = false;
        result["message"] = "No resource with the required skill could be found.";
    }

    sqlite3_close(db);
    std::cout << result.dump(4) << std::endl;
}

void complete_task(int task_id) {
    sqlite3* db;
    sqlite3_stmt* stmt;
    json result;

    if (sqlite3_open("resource_matching.db", &db)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    int resource_id = -1;
    sqlite3_prepare_v2(db, "SELECT resource_id FROM Assignments WHERE task_id = ?;", -1, &stmt, 0);
    sqlite3_bind_int(stmt, 1, task_id);
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        resource_id = sqlite3_column_int(stmt, 0);
    }
    sqlite3_finalize(stmt);

    if (resource_id != -1) {
        const char* update_sql = "UPDATE Tasks SET status = 'Completed', completed_by_resource_id = ?, completion_date = ? WHERE task_id = ?;";
        sqlite3_prepare_v2(db, update_sql, -1, &stmt, 0);
        sqlite3_bind_int(stmt, 1, resource_id);
        sqlite3_bind_text(stmt, 2, format_date(std::chrono::system_clock::now()).c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 3, task_id);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);

        sqlite3_prepare_v2(db, "DELETE FROM Assignments WHERE task_id = ?;", -1, &stmt, 0);
        sqlite3_bind_int(stmt, 1, task_id);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);

        result["success"] = true;
    } else {
        result["success"] = false;
    }
    
    sqlite3_close(db);
    std::cout << result.dump(4) << std::endl;
}

void add_resource(const std::string& name, const std::vector<std::string>& skills) {
    sqlite3* db;
    sqlite3_stmt* stmt;
    json result;

    if (sqlite3_open("resource_matching.db", &db)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    // 1 - Insert into Resources table
    sqlite3_prepare_v2(db, "INSERT INTO Resources (resource_name) VALUES (?);", -1, &stmt, 0);
    sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);
    if (sqlite3_step(stmt) != SQLITE_DONE) {
        sqlite3_finalize(stmt);
        sqlite3_close(db);
        throw std::runtime_error("Failed to insert new resource. Name might already exist.");
    }
    sqlite3_finalize(stmt);
    long long resource_id = sqlite3_last_insert_rowid(db);

    // 2 - Insert into Resource_Skills table with skills
    sqlite3_prepare_v2(db, "INSERT INTO Resource_Skills (resource_id, skill) VALUES (?, ?);", -1, &stmt, 0);
    for (const auto& skill : skills) {
        sqlite3_bind_int(stmt, 1, resource_id);
        sqlite3_bind_text(stmt, 2, skill.c_str(), -1, SQLITE_STATIC);
        if (sqlite3_step(stmt) != SQLITE_DONE) {
            sqlite3_finalize(stmt);
            sqlite3_close(db);
            throw std::runtime_error("Failed to insert skill '" + skill + "' for resource '" + name + "'.");
        }
        sqlite3_reset(stmt);
    }
    sqlite3_finalize(stmt);

    // 3 - Insert default availability for the new resource
    auto today = std::chrono::system_clock::now();
    auto one_year_later = today + std::chrono::hours(365 * 24);
    std::string start_avail = format_date(today);
    std::string end_avail = format_date(one_year_later);
    
    sqlite3_prepare_v2(db, "INSERT INTO Resource_Availability (resource_id, available_from, available_to) VALUES (?, ?, ?);", -1, &stmt, 0);
    sqlite3_bind_int(stmt, 1, resource_id);
    sqlite3_bind_text(stmt, 2, start_avail.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, end_avail.c_str(), -1, SQLITE_STATIC);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    result["success"] = true;
    result["message"] = "Resource '" + name + "' added successfully.";
    
    sqlite3_close(db);
    std::cout << result.dump(4) << std::endl;
}

int main(int argc, char* argv[]) {
    try {
        if (argc < 2) {
            std::cerr << "Usage: " << argv[0] << " <project_id> | --init | --allocate ... | --complete <task_id> | --add_resource <name> [skills...]" << std::endl;
            return 1;
        }

        std::string mode = argv[1];
        if (mode == "--init") {
            setup_database();
        } else if (mode == "--allocate") {
            if (argc != 6) return 1;
            allocate_task(argv[2], argv[3], argv[4], std::stoi(argv[5]));
        } else if (mode == "--complete") {
            if (argc != 3) return 1;
            complete_task(std::stoi(argv[2]));
        } else if (mode == "--add_resource") {
            if (argc < 4) {
                std::cerr << "Usage for --add_resource: <name> <skill1> [skill2]..." << std::endl;
                return 1;
            }
            std::string name = argv[2];
            std::vector<std::string> skills;
            for (int i = 3; i < argc; ++i) {
                skills.push_back(argv[i]);
            }
            add_resource(name, skills);
        } else {
            find_matches(std::stoi(mode));
        }
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
