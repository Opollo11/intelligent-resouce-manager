import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(layout="wide")
st.title("Intelligent Task Manager")

# --- Data Fetching Functions (remain the same) ---
def get_api_data(endpoint):
    try:
        res = requests.get(f"{API_URL}/{endpoint}")
        return res.json() if res.status_code == 200 else []
    except requests.exceptions.ConnectionError:
        return None

projects_list = get_api_data("projects")
skills_list = get_api_data("skills")

# --- Main App ---
if projects_list is None or skills_list is None:
    st.error("Connection Error: Make sure the Python API server is running (`python api.py`).")
else:
    projects_map = {p['name']: p['id'] for p in projects_list}
    
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
        
        selected_project_name = st.selectbox("Select a Project", options=projects_map.keys())
        
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
                    st.write("No tasks found for this project.")

    # Tab 2: Allocate a new task
    with tab2:
        st.header("Allocate a New Task by Priority")
        st.info("The system will first try to find a completely free resource. If none are available, it will assign the task to the qualified resource with the lightest workload.")

        with st.form("allocation_form"):
            # New improved project selection
            st.write("**Select an Existing Project OR Enter a New One**")
            existing_project = st.selectbox("Select Existing Project", options=[""] + list(projects_map.keys()))
            new_project_name = st.text_input("Or, Create New Project", placeholder="e.g., Marketing Campaign Q4")
            
            st.markdown("---")
            task_name = st.text_input("New Task Name", placeholder="e.g., Refactor Authentication Module")
            col1, col2 = st.columns(2)
            with col1:
                required_skill = st.selectbox("Required Skill", options=skills_list)
            with col2:
                duration_hours = st.number_input("Hours Required for Task", min_value=1, value=8)

            submitted = st.form_submit_button("Allocate Task")

            if submitted:
                project_name = new_project_name if new_project_name else existing_project
                if not all([project_name, task_name, required_skill, duration_hours]):
                    st.warning("Please ensure a project is selected or created, and all task fields are filled.")
                else:
                    with st.spinner("Running allocation algorithm..."):
                        task_data = {
                            "project_name": project_name,
                            "task_name": task_name,
                            "skill": required_skill,
                            "duration_hours": duration_hours
                        }
                        response = requests.post(f"{API_URL}/tasks", json=task_data)
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("success"):
                                st.success(f"✅ {result['message']} Assigned to: **{result['allocated_to']}**")
                            else:
                                st.error(f"❌ {result['message']}")
                        else:
                            st.error(f"An API error occurred: {response.status_code} - {response.text}")
    
    # Tab 3: View and Complete Assignments
    with tab3:
        st.header("Current Active Assignments")
        st.info("Check the box next to a task to mark it as complete and free up the resource.")
        
        if st.button("Refresh Active Assignments"):
            st.rerun()

        assignments_data = get_api_data("resource_assignments")
        if assignments_data:
            for resource in assignments_data:
                # ... (This section's code for checkboxes remains the same)
                pass
        else:
            st.info("No tasks are currently assigned to any resources.")

    # Tab 4: New tab to show completion history
    with tab4:
        st.header("Completed Task History")
        
        if st.button("Refresh History"):
            st.rerun()
            
        with st.spinner("Fetching completion history..."):
            completed_data = get_api_data("completed_tasks")
            if completed_data:
                df_completed = pd.DataFrame(completed_data)
                df_completed.rename(
                    columns={
                        'project_name': 'Project',
                        'task_name': 'Task',
                        'completed_by': 'Completed By',
                        'completion_date': 'Date Completed'
                    },
                    inplace=True
                )
                st.dataframe(df_completed, hide_index=True, use_container_width=True)
            else:
                st.info("No tasks have been completed yet.")