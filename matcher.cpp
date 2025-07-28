#include <iostream>
#include <string>
#include <vector>
#include <stdexcept>
#include "sqlite3.h"
#include "json.hpp"

using json = nlohmann::json;

void execute_sql(sqlite3* db, const char* sql) {
    char* err_msg = 0;
    int rc = sqlite3_exec(db, sql, 0, 0, &err_msg);
    if (rc != SQLITE_OK) {
        std::string error = "SQL error: " + std::string(err_msg);
        sqlite3_free(err_msg);
        throw std::runtime_error(error);
    }
}

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
    
    execute_sql(db, "CREATE TABLE Projects (project_id INTEGER PRIMARY KEY, project_name TEXT);");
    execute_sql(db, "CREATE TABLE Tasks (task_id INTEGER PRIMARY KEY, project_id INTEGER, task_name TEXT, required_skill TEXT, schedule_from TEXT, schedule_to TEXT);");
    execute_sql(db, "CREATE TABLE Resources (resource_id INTEGER PRIMARY KEY, resource_name TEXT);");
    execute_sql(db, "CREATE TABLE Resource_Skills (resource_id INTEGER, skill TEXT);");
    execute_sql(db, "CREATE TABLE Resource_Availability (availability_id INTEGER PRIMARY KEY, resource_id INTEGER, available_from TEXT, available_to TEXT);");

    execute_sql(db, "BEGIN TRANSACTION;");
    execute_sql(db, "INSERT INTO Projects VALUES (1, 'E-commerce Website'), (2, 'Mobile Banking App');");
    execute_sql(db, "INSERT INTO Tasks VALUES (1, 1, 'Setup Database', 'SQL', '2025-08-01', '2025-08-05'), (2, 1, 'Develop Backend API', 'C#', '2025-08-06', '2025-08-15'), (3, 1, 'Create UI Components', 'Web Services/Rest API', '2025-08-10', '2025-08-20'), (4, 2, 'Design Database Schema', 'Mongo DB', '2025-09-01', '2025-09-05'), (5, 2, 'Implement Core Logic', 'Node.JS', '2025-09-06', '2025-09-20');");
    execute_sql(db, "INSERT INTO Resources VALUES (101, 'Ram'), (102, 'Shyam'), (103, 'Kiran'), (104, 'Dhina');");
    execute_sql(db, "INSERT INTO Resource_Skills VALUES (101, 'SQL'), (101, 'C#'), (102, 'C#'), (102, 'Web Services/Rest API'), (103, 'Mongo DB'), (103, 'Node.JS'), (104, 'SQL'), (104, 'Node.JS');");
    execute_sql(db, "INSERT INTO Resource_Availability VALUES (1, 101, '2025-08-01', '2025-08-10'), (2, 102, '2025-08-10', '2025-08-25'), (3, 103, '2025-09-01', '2025-09-30'), (4, 104, '2025-08-01', '2025-08-15');");
    execute_sql(db, "COMMIT;");

    sqlite3_close(db);
}

void find_matches(int project_id) {
    sqlite3* db;
    sqlite3_stmt* stmt_tasks;
    sqlite3_stmt* stmt_resources;

    if (sqlite3_open_v2("resource_matching.db", &db, SQLITE_OPEN_READONLY, NULL)) {
        throw std::runtime_error("Can't open database: " + std::string(sqlite3_errmsg(db)));
    }

    const char* tasks_sql = "SELECT task_name, required_skill, schedule_from, schedule_to FROM Tasks WHERE project_id = ?;";
    if (sqlite3_prepare_v2(db, tasks_sql, -1, &stmt_tasks, 0) != SQLITE_OK) {
        throw std::runtime_error("Failed to prepare task statement: " + std::string(sqlite3_errmsg(db)));
    }
    sqlite3_bind_int(stmt_tasks, 1, project_id);

    json results = json::array();

    // for each task
    while (sqlite3_step(stmt_tasks) == SQLITE_ROW) {
        json task_result;
        task_result["task_name"] = reinterpret_cast<const char*>(sqlite3_column_text(stmt_tasks, 0));
        std::string required_skill = reinterpret_cast<const char*>(sqlite3_column_text(stmt_tasks, 1));
        std::string schedule_from = reinterpret_cast<const char*>(sqlite3_column_text(stmt_tasks, 2));
        std::string schedule_to = reinterpret_cast<const char*>(sqlite3_column_text(stmt_tasks, 3));
        
        task_result["required_skill"] = required_skill;
        task_result["schedule"] = schedule_from + " to " + schedule_to;

        const char* resources_sql = "SELECT R.resource_id, R.resource_name FROM Resources R JOIN Resource_Skills RS ON R.resource_id = RS.resource_id JOIN Resource_Availability RA ON R.resource_id = RA.resource_id WHERE RS.skill = ? AND RA.available_from <= ? AND RA.available_to >= ?;";
        if (sqlite3_prepare_v2(db, resources_sql, -1, &stmt_resources, 0) != SQLITE_OK) {
            throw std::runtime_error("Failed to prepare resource statement: " + std::string(sqlite3_errmsg(db)));
        }

        sqlite3_bind_text(stmt_resources, 1, required_skill.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt_resources, 2, schedule_from.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt_resources, 3, schedule_to.c_str(), -1, SQLITE_STATIC);

        json matched_resources = json::array();
        
        while (sqlite3_step(stmt_resources) == SQLITE_ROW) {
            json resource;
            resource["id"] = sqlite3_column_int(stmt_resources, 0);
            resource["name"] = reinterpret_cast<const char*>(sqlite3_column_text(stmt_resources, 1));
            matched_resources.push_back(resource);
        }
        sqlite3_finalize(stmt_resources);

        task_result["matched_resources"] = matched_resources;
        results.push_back(task_result);
    }
    sqlite3_finalize(stmt_tasks);
    sqlite3_close(db);

    std::cout << results.dump(4) << std::endl;
}

int main(int argc, char* argv[]) {
    try {
        if (argc < 2) {
            std::cerr << "Usage: " << argv[0] << " --init | <project_id>" << std::endl;
            return 1;
        }

        std::string arg = argv[1];
        if (arg == "--init") {
            setup_database();
            std::cout << "Database initialized successfully." << std::endl;
        } else {
            int project_id = std::stoi(arg);
            find_matches(project_id);
        }
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}