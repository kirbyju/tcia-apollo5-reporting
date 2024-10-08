import streamlit as st
import pandas as pd
from tcia_utils import nbia
import datetime
import plotly.express as px

def preprocess_age(age):
    if pd.isna(age) or age == 'None':
        return None
    return int(age.rstrip('Y'))

def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a UI on top of a dataframe to let viewers filter columns

    Args:
        df (pd.DataFrame): Original dataframe

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    modify = st.checkbox("Add filters")

    if not modify:
        return df

    df = df.copy()

    # Try to convert datetimes into a standard format (datetime, no timezone)
    for col in df.columns:
        if is_object_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                pass

        if is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)

    modification_container = st.container()

    with modification_container:
        to_filter_columns = st.multiselect("Filter dataframe on", df.columns)
        for column in to_filter_columns:
            left, right = st.columns((1, 20))
            left.write("↳")
            # Treat columns with < 10 unique values as categorical
            if is_categorical_dtype(df[column]) or df[column].nunique() < 10:
                user_cat_input = right.multiselect(
                    f"Values for {column}",
                    df[column].unique(),
                    default=list(df[column].unique()),
                )
                df = df[df[column].isin(user_cat_input)]
            elif is_numeric_dtype(df[column]):
                _min = float(df[column].min())
                _max = float(df[column].max())
                step = (_max - _min) / 100
                user_num_input = right.slider(
                    f"Values for {column}",
                    _min,
                    _max,
                    (_min, _max),
                    step=step,
                )
                df = df[df[column].between(*user_num_input)]
            elif is_datetime64_any_dtype(df[column]):
                user_date_input = right.date_input(
                    f"Values for {column}",
                    value=(
                        df[column].min(),
                        df[column].max(),
                    ),
                )
                if len(user_date_input) == 2:
                    user_date_input = tuple(map(pd.to_datetime, user_date_input))
                    start_date, end_date = user_date_input
                    df = df.loc[df[column].between(start_date, end_date)]
            else:
                user_text_input = right.text_input(
                    f"Substring or regex in {column}",
                )
                if user_text_input:
                    df = df[df[column].str.contains(user_text_input)]

    return df

def generate_monthly_report():
    # get list of all collections
    collections_json = nbia.getCollections()
    collections = [item['Collection'] for item in collections_json]

    # select only APOLLO-5 collections
    collectionSubset = [item for item in collections if "APOLLO-5" in item]
    collections = collectionSubset
    st.write(f"{len(collections)} APOLLO-5 collections are being analyzed.")
    st.write(collections)

    # get inventory of studies
    studies = pd.DataFrame()

    for collection in collections:
        studyDescription = nbia.getStudy(collection)
        studies = pd.concat([studies, pd.DataFrame(studyDescription)], ignore_index=True)

    # get unique patient IDs from studies dataframe
    unique_patient_ids = studies['PatientID'].unique()

    # Convert the unique patient IDs to a comma-separated string
    patient_id_list = ",".join(unique_patient_ids)

    # call getAdvancedQCSearch to get collection//site info for these subjects
    criteria_values = [("patientID", patient_id_list)]
    series_site_info = nbia.getAdvancedQCSearch(criteria_values, format="df")

    # Rename the 'study' column to 'StudyInstanceUID'
    series_site_info = series_site_info.rename(columns={'study': 'StudyInstanceUID'})

    # extract series column from series_site_info df to list
    series_list = series_site_info['series'].tolist()

    # use nbia.getSeriesList to look up series metadata
    series_info = nbia.getSeriesList(series_list, format="df")

    # for each unique Study UID value, calculate the sum of the Number of images column
    image_counts_by_study = series_info.groupby('Study UID')['Number of images'].sum().reset_index()

    # rename Number of images to ImageCount
    image_counts_by_study = image_counts_by_study.rename(columns={'Number of images': 'ImageCount'})

    # rename 'Study UID' to 'StudyInstanceUID'
    image_counts_by_study = image_counts_by_study.rename(columns={'Study UID': 'StudyInstanceUID'})

    # Drop all other columns except for 'StudyInstanceUID' and 'collectionSite'
    columns_to_keep = ['StudyInstanceUID', 'collectionSite']
    series_site_info = series_site_info[columns_to_keep]

    # Remove duplicates based on 'StudyInstanceUID' and 'collectionSite'
    series_site_info = series_site_info.drop_duplicates(subset=['StudyInstanceUID', 'collectionSite'])

    # Merge 'series_site_info' with 'studies' on 'StudyInstanceUID'
    apollo5_study_report = pd.merge(studies, series_site_info, on='StudyInstanceUID', how='left')

    # Merge the 'ImageCount' column from image_counts_by_study into apollo5_study_report
    apollo5_study_report = pd.merge(apollo5_study_report, image_counts_by_study, on='StudyInstanceUID', how='left')

    # drop unnecessary columns
    apollo5_study_report.drop(columns=['Collection', 'AdmittingDiagnosesDescription', 'PatientName'], inplace=True)

    # Split the 'collectionSite' column into 'Collection' and 'Site'
    apollo5_study_report[['Collection', 'Site']] = apollo5_study_report['collectionSite'].str.split('//', expand=True)

    # Drop the original 'collectionSite' column
    apollo5_study_report = apollo5_study_report.drop(columns=['collectionSite'])

    # Preprocess the PatientAge column
    apollo5_study_report['PatientAge_Numeric'] = apollo5_study_report['PatientAge'].apply(preprocess_age)

    # Define the new order of columns
    new_order = ['PatientID', 'Collection', 'Site', 'LongitudinalTemporalEventType', 'LongitudinalTemporalOffsetFromEvent', 'StudyDate', 'StudyInstanceUID', 'StudyDescription', 'SeriesCount', 'ImageCount', 'PatientAge', 'PatientAge_Numeric', 'PatientSex', 'EthnicGroup']

    # Reorder the columns
    apollo5_study_report = apollo5_study_report.reindex(columns=new_order)

    # save merged report to a CSV
    csv_filename = f"apollo5-monthly-report_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    apollo5_study_report.to_csv(csv_filename, index=False)

    return apollo5_study_report, csv_filename

def main():

    st.set_page_config(page_title="TCIA APOLLO-5 Reporting", layout="wide")
    st.sidebar.image("https://www.cancerimagingarchive.net/wp-content/uploads/2021/06/TCIA-Logo-01.png", use_column_width=True)
    st.title("TCIA APOLLO-5 Reporting")

    # Sidebar for login
    with st.sidebar:
        st.header("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        # Report selection dropdown
        report_options = ["Monthly Report"]
        selected_report = st.selectbox("Select Report", report_options)

        # Generate Report button
        generate_button = st.button("Generate Report")

    # Main content area
    if generate_button:
        if username and password:
            try:
                status_code = nbia.getToken(username, password)
                if status_code == 200:
                    st.success("Login successful!")

                    if selected_report == "Monthly Report":
                        with st.spinner("Generating Monthly Report..."):
                            df, csv_filename = generate_monthly_report()

                        st.success("Monthly Report generated successfully!")

                        # Display the dataframe
                        st.subheader("Monthly Report Data")
                        st.dataframe(filter_dataframe(df))

                        # Offer CSV download
                        st.download_button(
                            label="Download CSV",
                            data=df.to_csv(index=False),
                            file_name=csv_filename,
                            mime="text/csv"
                        )

                        # Visualizations
                        st.subheader("Visualizations")

                        col1, col2 = st.columns(2)

                        with col1:
                            # PatientID by Collection
                            patient_counts = df.groupby('Collection')['PatientID'].nunique().reset_index()
                            fig_collection = px.pie(patient_counts, values='PatientID', names='Collection',
                                                    title="PatientID by Collection")
                            st.plotly_chart(fig_collection)

                            # Patient Sex distribution (unique PatientIDs)
                            sex_counts = df.drop_duplicates('PatientID')['PatientSex'].value_counts()
                            fig_sex = px.pie(values=sex_counts.values, names=sex_counts.index,
                                             title="Distribution of Patient Sex (Unique PatientIDs)")
                            st.plotly_chart(fig_sex)

                        with col2:
                            # Image Count by Collection
                            fig_image_count = px.bar(df.groupby('Collection')['ImageCount'].sum().reset_index(),
                                                     x='Collection', y='ImageCount', title="Total Image Count by Collection")
                            st.plotly_chart(fig_image_count)

                            # Patient Age distribution (ordered from youngest to oldest)
                            age_data = df.drop_duplicates('PatientID')
                            age_data = age_data[age_data['PatientAge_Numeric'].notna()]
                            fig_age = px.histogram(age_data, x='PatientAge_Numeric',
                                                   title="Distribution of Patient Ages (Unique PatientIDs)")
                            fig_age.update_xaxes(title_text="Patient Age (Years)")
                            st.plotly_chart(fig_age)

                        # LongitudinalTemporalOffsetFromEvent distribution
                        fig_offset = px.histogram(df, x='LongitudinalTemporalOffsetFromEvent',
                                                  title="Distribution of Days Since Diagnosis",
                                                  labels={'LongitudinalTemporalOffsetFromEvent': 'Days Since Diagnosis'})
                        st.plotly_chart(fig_offset)

                        # Number of unique StudyDate values for each PatientID (sorted in descending order)
                        study_dates_per_patient = df.groupby('PatientID')['StudyDate'].nunique().reset_index()
                        study_dates_per_patient = study_dates_per_patient.rename(columns={'StudyDate': 'Number of Study Dates'})
                        study_dates_per_patient = study_dates_per_patient.sort_values('Number of Study Dates', ascending=False)
                        fig_study_dates = px.bar(study_dates_per_patient, x='PatientID', y='Number of Study Dates',
                                                 title="Number of Unique Study Dates per Patient")
                        st.plotly_chart(fig_study_dates)

                else:
                    st.error("Login failed. Please check your credentials.")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
        else:
            st.warning("Please enter your username and password.")

if __name__ == "__main__":
    main()
