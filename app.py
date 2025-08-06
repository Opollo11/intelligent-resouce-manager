import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(layout="wide")
st.title("Intelligent Task Manager")

# --- Data Fetching Functions ---
def get_api_data(endpoint):
    try:
        res = requests.get(f"{API_URL}/{endpoint}")
        if res.status_code == 200:
            return res.json()
    except requests.exceptions.ConnectionError:
        return None
    return []

# --- Main App ---
def main():
    projects_list = get_api_data("projects")
    skills_list = get_api_data("skills")
    resources_list = get_api_data("resources")

    if projects_list is None or skills_list is None or resources_list is None:
        st.error("Connection Error: Make sure the Python API server is running (`python api.py`).")
        return

    projects_map = {p['name']: p['id'] for p in projects_list}
    resources_map = {r['name']: r['id'] for r in resources_list}
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Project Task Matching", 
        "➕ Allocate New Task", 
        "📋 View & Complete Assignments",
        "📜 Completion History"
    ])

    # Tab 1: View potential matches for existing tasks
    with tab1:
        st.header("View Potential Resource Matches")
        st.info("Select a project to see all existing tasks and every resource who is qualified and available to work on them.")
        
        selected_project_name = st.selectbox("Select a Project", options=projects_map.keys(), key="tab1_project_selector")
        
        if selected_project_name:
            project_id = projects_map[selected_project_name]
            with st.spinner(f"Finding potential matches for '{selected_project_name}'..."):
                match_data = get_api_data(f"match_resources?project_id={project_id}")
                if match_data:
                    for task in match_data:
                        st.subheader(f"Task: {task['task_name']}")
                        st.write(f"**Required Skill:** {task['required_skill']} | **Schedule:** {task['schedule']}")
                        if task['matched_resources']:
                            df = pd.DataFrame(task['matched_resources'])
                            st.dataframe(df, hide_index=True)
                        else:
                            st.warning("No potential resources found for this task's skill and schedule.")
                        st.markdown("---")
                else:
                    st.write("No unassigned tasks found for this project.")

    # Tab 2: Allocate a new task
    with tab2:
        st.header("Allocate a New Task")
        
        with st.form("allocation_form"):
            st.write("**1. Define the Project & Task**")
            project_name_input = st.text_input("Project Name", placeholder="Enter existing or new project name")
            task_name = st.text_input("New Task Name", placeholder="e.g., Refactor Authentication Module")
            
            st.write("**2. Define Task Requirements**")
            col1, col2 = st.columns(2)
            with col1:
                required_skill = st.selectbox("Required Skill", options=skills_list)
            with col2:
                duration_hours = st.number_input("Hours Required", min_value=1, value=8)

            st.write("**3. Assign a Resource (Optional)**")
            resource_name = st.selectbox("Assign to Resource", options=["Auto-Assign (Recommended)"] + list(resources_map.keys()))

            submitted_task = st.form_submit_button("Allocate Task")

            if submitted_task:
                if not all([project_name_input, task_name, required_skill, duration_hours]):
                    st.warning("Please ensure Project Name, Task Name, Skill, and Duration are filled out.")
                else:
                    with st.spinner("Running allocation algorithm..."):
                        task_data = {
                            "project_name": project_name_input,
                            "task_name": task_name,
                            "skill": required_skill,
                            "duration_hours": duration_hours
                        }
                        if resource_name != "Auto-Assign (Recommended)":
                            task_data["resource_id"] = resources_map[resource_name]
                        
                        response = requests.post(f"{API_URL}/tasks", json=task_data)
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("success"):
                                st.success(f"✅ {result.get('message')} Assigned to: **{result.get('allocated_to', 'N/A')}**")
                            else:
                                st.error(f"❌ {result.get('message', 'An unknown error occurred.')}")
                        else:
                            st.error(f"An API error occurred: {response.status_code} - {response.text}")
        
        with st.expander("Add a New Resource to the Team"):
            with st.form("new_resource_form"):
                st.subheader("New Resource Details")
                new_name = st.text_input("Resource Name")
                new_skills = st.multiselect("Select Skills", options=skills_list)
                submitted_resource = st.form_submit_button("Add Resource")

                if submitted_resource:
                    if not new_name or not new_skills:
                        st.warning("Please provide a name and at least one skill.")
                    else:
                        with st.spinner(f"Adding '{new_name}' to the team..."):
                            resource_data = {"name": new_name, "skills": new_skills}
                            response = requests.post(f"{API_URL}/resources", json=resource_data)
                            if response.status_code == 200 and response.json().get("success"):
                                st.success(response.json().get("message"))
                                st.info("New resource will be available in dropdowns on next refresh.")
                            else:
                                st.error(f"API Error: {response.status_code} - {response.text}")
    
    # Tab 3: View and Complete Assignments
    with tab3:
        st.header("Current Active Assignments")
        st.info("Check the box next to a task to mark it as complete and free up the resource.")
        
        if st.button("Refresh Active Assignments"):
            st.rerun()

        assignments_data = get_api_data("resource_assignments")
        if assignments_data:
            for resource in assignments_data:
                st.subheader(f"Resource: {resource['resource_name']}")
                for task in resource['assigned_tasks']:
                    task_id = task['task_id']
                    col1, col2, col3 = st.columns([1, 4, 2])
                    with col1:
                        is_complete = st.checkbox("✔", key=f"complete_{task_id}", help="Mark as complete")
                    with col2:
                        st.write(f"{task['task_name']} ({task['duration_hours']} hrs)")
                    with col3:
                        st.write(task['project_name'])
                    if is_complete:
                        with st.spinner(f"Completing '{task['task_name']}'..."):
                            res = requests.delete(f"{API_URL}/tasks/{task_id}")
                            if res.status_code == 200 and res.json().get("success"):
                                st.toast(f"Task '{task['task_name']}' completed!", icon="🎉")
                                st.rerun()
                            else:
                                st.error("Failed to complete the task.")
        else:
            st.info("No tasks are currently assigned to any resources.")
            
    # Tab 4: Completion History
    with tab4:
        st.header("Completed Task History")
        
        if st.button("Refresh History"):
            st.rerun()
            
        with st.spinner("Fetching completion history..."):
            completed_data = get_api_data("completed_tasks")
            if completed_data:
                df_completed = pd.DataFrame(completed_data)
                df_completed.rename(columns={'project_name': 'Project', 'task_name': 'Task', 'completed_by': 'Completed By', 'completion_date': 'Date Completed'}, inplace=True)
                st.dataframe(df_completed, hide_index=True, use_container_width=True)
            else:
                st.info("No tasks have been completed yet.")

if __name__ == "__main__":
    main()
