import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(layout="wide")
st.title("Resource Skill Matching Dashboard")

tab1, tab2 = st.tabs(["Project Task Matching", "Resource Assignments"])

try:
    with tab1:
        st.header("Find Resource Matches for Project Tasks")
        project_response = requests.get(f"{API_URL}/projects")

        if project_response.status_code == 200:
            projects = project_response.json()
            project_names = {p['name']: p['id'] for p in projects}
            selected_project_name = st.selectbox(
                "Select a Project",
                options=project_names.keys(),
                key="project_selector"
            )

            if selected_project_name:
                project_id = project_names[selected_project_name]
                with st.spinner('Asking the C++ backend for matches...'):
                    match_response = requests.get(f"{API_URL}/match_resources?project_id={project_id}")
                    if match_response.status_code == 200:
                        results = match_response.json()
                        st.subheader(f"Matching Results for: {selected_project_name}")
                        for result in results:
                            st.subheader(f"Task: {result['task_name']}")
                            st.write(f"**Required Skill:** {result['required_skill']}")
                            st.write(f"**Schedule:** {result['schedule']}")
                            if result['matched_resources']:
                                df = pd.DataFrame(result['matched_resources'])
                                df.rename(columns={'id': 'Resource ID', 'name': 'Resource Name'}, inplace=True)
                                st.dataframe(df)
                            else:
                                st.warning("No available resources found for this task.")
                            st.markdown("---")
                    else:
                        st.error(f"API Error: {match_response.status_code} - {match_response.text}")
        else:
            st.error("Could not connect to the API to fetch projects.")

    with tab2:
        st.header("View Task Assignments per Resource")
        with st.spinner("Fetching resource assignment data..."):
            assignments_response = requests.get(f"{API_URL}/resource_assignments")

            if assignments_response.status_code == 200:
                assignments_data = assignments_response.json()
                if assignments_data:
                    st.write("This view shows a detailed breakdown of tasks each resource is matched to.")
                    for resource in assignments_data:
                        st.subheader(f"Resource: {resource['resource_name']}")
                        if resource['assigned_tasks']:
                            df_tasks = pd.DataFrame(resource['assigned_tasks'])
                            df_tasks.rename(
                                columns={'task_name': 'Task Name', 'project_name': 'Project Name'},
                                inplace=True
                            )
                            st.dataframe(df_tasks, hide_index=True)
                        else:
                            st.info("No tasks are currently assigned to this resource.")
                        st.markdown("---")
                else:
                    st.info("No task assignment data found for any resources.")
            else:
                st.error(f"API Error: {assignments_response.status_code} - {assignments_response.text}")

except requests.exceptions.ConnectionError:
    st.error("Connection Error: Make sure the Python API server is running (`python api.py`).")
