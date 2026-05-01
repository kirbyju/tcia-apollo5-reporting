import streamlit as st
import pandas as pd
import nbia_utils as nbia
import datetime
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor
import os
import glob
from pandas.api.types import (
    is_categorical_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
    is_object_dtype,
)

def get_latest_report(report_type="monthly"):
    """
    Finds the most recent report CSV file based on report_type.
    """
    if report_type == "monthly":
        pattern = 'APOLLO-5-monthly-report_*.csv'
    elif report_type == "series":
        pattern = 'APOLLO-5-series-report_*.csv'
    else:
        return None

    list_of_files = glob.glob(pattern)
    if not list_of_files:
        return None
    latest_file = max(list_of_files, key=os.path.getctime)
    return latest_file

def preprocess_age(age):
    if pd.isna(age) or age == 'None':
        return None
    try:
        return int(str(age).rstrip('Y'))
    except ValueError:
        return None

def get_target_month():
    """
    Returns the first and last day of the previous month.
    """
    today = datetime.date.today()
    first_day_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_day_of_this_month - datetime.timedelta(days=1)
    first_day_of_last_month = last_day_of_last_month.replace(day=1)
    return first_day_of_last_month, last_day_of_last_month

def display_what_changed(df_series):
    """
    Displays the 'What Changed' table, overall summary stats, and growth charts.
    """
    if df_series is None or df_series.empty:
        st.warning("No series data available for 'What Changed' analysis.")
        return

    st.divider()
    st.header("What Changed (Last Full Month)")

    start_date, end_date = get_target_month()
    st.write(f"Reporting changes for: **{start_date.strftime('%B %Y')}**")

    # Ensure MaxSubmissionTimestamp is datetime
    if 'MaxSubmissionTimestamp' not in df_series.columns:
        st.error("Column 'MaxSubmissionTimestamp' not found in series data. Cannot perform 'What Changed' analysis.")
        return

    df_series = df_series.copy()
    df_series['MaxSubmissionTimestamp'] = pd.to_datetime(df_series['MaxSubmissionTimestamp'])

    # Target month filter
    mask_target = (df_series['MaxSubmissionTimestamp'].dt.date >= start_date) & \
                  (df_series['MaxSubmissionTimestamp'].dt.date <= end_date)
    mask_prior = (df_series['MaxSubmissionTimestamp'].dt.date < start_date)

    new_series_df = df_series[mask_target].copy()
    prior_series_df = df_series[mask_prior].copy()

    if new_series_df.empty:
        st.info(f"No new items found for {start_date.strftime('%B %Y')}.")
    else:
        # Identify New vs Updated studies
        prior_studies = set(prior_series_df['StudyInstanceUID'].unique())
        target_studies_uids = new_series_df['StudyInstanceUID'].unique()

        new_studies = set()
        updated_studies = set()

        for sid in target_studies_uids:
            if sid in prior_studies:
                updated_studies.add(sid)
            else:
                new_studies.add(sid)

        # Table per patient
        # Columns: Collection, Patient ID, Site, New study count, new series count
        patient_stats = new_series_df.groupby('PatientID').agg({
            'Collection': 'unique',
            'Site': 'unique',
            'StudyInstanceUID': [
                lambda x: len(set(x) & new_studies),
                lambda x: len(set(x) & updated_studies)
            ],
            'SeriesInstanceUID': 'nunique'
        }).reset_index()

        patient_stats.columns = ['PatientID', 'Collections', 'Sites', 'New study count', 'Updated study count', 'new series count']

        # Check for multiple collections/sites
        for idx, row in patient_stats.iterrows():
            if len(row['Collections']) > 1 or len(row['Sites']) > 1:
                st.warning(f"Patient {row['PatientID']} is associated with multiple collections/sites: {row['Collections']} / {row['Sites']}")

        # Format for display
        patient_stats['Collection'] = patient_stats['Collections'].apply(lambda x: ', '.join(map(str, sorted(x))))
        patient_stats['Site'] = patient_stats['Sites'].apply(lambda x: ', '.join(map(str, sorted(x))))

        display_table = patient_stats[['Collection', 'PatientID', 'Site', 'New study count', 'Updated study count', 'new series count']]
        st.subheader("Changes by Patient")
        st.dataframe(display_table, use_container_width=True)

        # Totals at the bottom of the table
        total_collections_updated = new_series_df['Collection'].nunique()
        total_subjects_updated = new_series_df['PatientID'].nunique()
        total_sites_updated = new_series_df['Site'].nunique()
        total_studies_new = len(new_studies)
        total_studies_updated = len(updated_studies)
        total_series_added = new_series_df['SeriesInstanceUID'].nunique()

        st.subheader("Summary of Changes")
        col_t1, col_t2, col_t3, col_t4, col_t5, col_t6 = st.columns(6)
        col_t1.metric("Collections Updated", total_collections_updated)
        col_t2.metric("Subjects Updated", total_subjects_updated)
        col_t3.metric("Sites Updated", total_sites_updated)
        col_t4.metric("New Studies Added", total_studies_new)
        col_t5.metric("Existing Studies Updated", total_studies_updated)
        col_t6.metric("New Series Added", total_series_added)

    # Overall summary stats (always show for entire filtered dataset)
    st.divider()
    st.header("Overall Summary Stats")
    total_patients_inv = df_series['PatientID'].nunique()
    total_studies_inv = df_series['StudyInstanceUID'].nunique()
    total_series_inv = df_series['SeriesInstanceUID'].nunique()
    total_images_inv = df_series['ImageCount'].sum()
    total_size_bytes = df_series['FileSize'].sum()
    total_size_tb = total_size_bytes / 1e12

    col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
    col_s1.metric("Total Subjects", total_patients_inv)
    col_s2.metric("Total Studies", total_studies_inv)
    col_s3.metric("Total Series", total_series_inv)
    col_s4.metric("Total Images", f"{total_images_inv:,}")
    col_s5.metric("Total Size (TB)", f"{total_size_tb:.2f}")

    # Growth charts
    st.divider()
    st.header("Growth Over Time")

    df_growth = df_series.dropna(subset=['MaxSubmissionTimestamp']).sort_values('MaxSubmissionTimestamp')
    if not df_growth.empty:
        df_growth['Month'] = df_growth['MaxSubmissionTimestamp'].dt.to_period('M').dt.to_timestamp()

        # Cumulative stats by month
        monthly_groups = df_growth.groupby('Month')

        months = []
        cum_patients = []
        cum_studies = []
        cum_series = []
        cum_images = []
        cum_size = []

        all_patients = set()
        all_studies = set()
        total_series_count = 0
        total_images_count = 0
        total_size_count = 0

        for month, group in monthly_groups:
            months.append(month)
            all_patients.update(group['PatientID'].unique())
            all_studies.update(group['StudyInstanceUID'].unique())
            total_series_count += group['SeriesInstanceUID'].nunique()
            total_images_count += group['ImageCount'].sum()
            total_size_count += group['FileSize'].sum()

            cum_patients.append(len(all_patients))
            cum_studies.append(len(all_studies))
            cum_series.append(total_series_count)
            cum_images.append(total_images_count)
            cum_size.append(total_size_count / 1e12)

        growth_df = pd.DataFrame({
            'Month': months,
            'Cumulative Patients': cum_patients,
            'Cumulative Studies': cum_studies,
            'Cumulative Series': cum_series,
            'Cumulative Images': cum_images,
            'Cumulative Size (TB)': cum_size
        })

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_p_s = px.line(growth_df, x='Month', y=['Cumulative Patients', 'Cumulative Studies'], title="Growth of Patients and Studies")
            st.plotly_chart(fig_p_s, use_container_width=True)

            fig_i = px.line(growth_df, x='Month', y='Cumulative Images', title="Growth of Images")
            st.plotly_chart(fig_i, use_container_width=True)

        with col_g2:
            fig_ser = px.line(growth_df, x='Month', y='Cumulative Series', title="Growth of Series")
            st.plotly_chart(fig_ser, use_container_width=True)

            fig_sz = px.line(growth_df, x='Month', y='Cumulative Size (TB)', title="Growth of Data Size")
            st.plotly_chart(fig_sz, use_container_width=True)
    else:
        st.info("No submission timestamp data available for growth charts.")

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

def generate_monthly_report(name):
    # get list of all collections
    if name == "VAREPOP-APOLLO":
        collections = ['VAREPOP-APOLLO']
    else:
        collections_json = nbia.getCollections()
        collections = [item['Collection'] for item in collections_json]

        # select only APOLLO collections
        collectionSubset = [item for item in collections if name in item]
        collections = collectionSubset
    st.write(f"{len(collections)} APOLLO collection(s) are being analyzed.")
    st.write(collections)

    # get inventory of studies
    with ThreadPoolExecutor(max_workers=10) as executor:
        study_results = list(executor.map(nbia.getStudy, collections))
    studies = pd.concat([pd.DataFrame(res) for res in study_results], ignore_index=True)

    # get unique patient IDs from studies dataframe
    unique_patient_ids = studies['PatientID'].unique().tolist()

    # call getAdvancedQCSearch to get collection//site info for these subjects in parallel chunks
    chunk_size = 500
    patient_chunks = [unique_patient_ids[i:i + chunk_size] for i in range(0, len(unique_patient_ids), chunk_size)]

    def fetch_qc_search(ids):
        id_list = ",".join(ids)
        criteria = [("patientID", id_list), ("qcstatus", "Visible")]
        return nbia.getAdvancedQCSearch(criteria, format="df")

    with ThreadPoolExecutor(max_workers=10) as executor:
        qc_results = list(executor.map(fetch_qc_search, patient_chunks))
    series_site_info = pd.concat(qc_results, ignore_index=True)

    # Rename the 'study' column to 'StudyInstanceUID'
    series_site_info = series_site_info.rename(columns={'study': 'StudyInstanceUID'})

    # extract series column from series_site_info df to list
    series_list = series_site_info['series'].tolist()

    # use nbia.getSeriesList to look up series metadata in parallel chunks
    series_chunks = [series_list[i:i + chunk_size] for i in range(0, len(series_list), chunk_size)]

    def fetch_series_info(s_list):
        return nbia.getSeriesList(s_list, format="df")

    with ThreadPoolExecutor(max_workers=10) as executor:
        series_results = list(executor.map(fetch_series_info, series_chunks))
    series_info = pd.concat(series_results, ignore_index=True)

    # Create series-level report
    series_report_site_info = series_site_info.copy()
    series_report_site_info[['Collection', 'Site']] = series_report_site_info['collectionSite'].str.split('//', expand=True)

    # Merge series_info with site info
    # Determine the series UID column in series_info
    series_uid_col = 'SeriesInstanceUID' if 'SeriesInstanceUID' in series_info.columns else ('Series Instance UID' if 'Series Instance UID' in series_info.columns else None)

    # Drop Collection and Site from series_info before merge if they already exist to avoid duplicates
    series_info_clean = series_info.copy()
    for col in ['Collection', 'Site']:
        if col in series_info_clean.columns:
            series_info_clean.drop(columns=[col], inplace=True)

    if series_uid_col:
        apollo5_series_report = pd.merge(
            series_info_clean,
            series_report_site_info[['series', 'Collection', 'Site']],
            left_on=series_uid_col,
            right_on='series',
            how='left'
        )
        if 'series' in apollo5_series_report.columns and series_uid_col != 'series':
            apollo5_series_report.drop(columns=['series'], inplace=True)
    else:
        # Fallback if we can't find the column, though unlikely
        apollo5_series_report = series_info_clean.copy()

    # Drop AnnotationsFlag if it exists
    if 'AnnotationsFlag' in apollo5_series_report.columns:
        apollo5_series_report.drop(columns=['AnnotationsFlag'], inplace=True)

    # Save series report to CSV
    series_csv_filename = f"{name}-series-report_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    apollo5_series_report.to_csv(series_csv_filename, index=False)

    # for each unique Study UID value, calculate the sum of the Number of images column
    image_counts_by_study = series_info.groupby('StudyInstanceUID')['ImageCount'].sum().reset_index()

    # Drop all other columns except for 'StudyInstanceUID' and 'collectionSite'
    columns_to_keep = ['StudyInstanceUID', 'collectionSite']
    series_site_info = series_site_info[columns_to_keep]

    # Remove duplicates based on 'StudyInstanceUID' and 'collectionSite'
    series_site_info = series_site_info.drop_duplicates(subset=['StudyInstanceUID', 'collectionSite'])

    # Split the 'collectionSite' column into 'Collection' and 'Site'
    series_site_info[['Collection', 'Site']] = series_site_info['collectionSite'].str.split('//', expand=True)

    # Group by StudyInstanceUID and aggregate Site and Collection
    # Since we are told a StudyInstanceUID can't be in different Collections, we can just take the first Collection
    series_site_info_agg = series_site_info.groupby('StudyInstanceUID').agg({
        'Collection': 'first',
        'Site': lambda x: ', '.join(sorted(x.unique()))
    }).reset_index()

    # Merge 'series_site_info_agg' with 'studies' on 'StudyInstanceUID' and 'Collection'
    # This avoids duplicate Collection columns (Collection_x, Collection_y)
    apollo5_study_report = pd.merge(studies, series_site_info_agg, on=['StudyInstanceUID', 'Collection'], how='left')

    # Merge the 'ImageCount' column from image_counts_by_study into apollo5_study_report
    apollo5_study_report = pd.merge(apollo5_study_report, image_counts_by_study, on='StudyInstanceUID', how='left')

    # Create a DataFrame with unique modalities per Study UID
    modalities_by_study = series_info.groupby('StudyInstanceUID')['Modality'].apply(lambda x: ', '.join(x.unique())).reset_index()

    # Rename columns for clarity and consistency
    modalities_by_study.rename(columns={'Modality': 'Unique Modalities'}, inplace=True)

    # Merge the 'Unique Modalities' column from modalities_by_study into apollo5_study_report
    apollo5_study_report = pd.merge(apollo5_study_report, modalities_by_study, on='StudyInstanceUID', how='left')

    # List of columns to drop
    columns_to_drop = ['AdmittingDiagnosesDescription', 'PatientName']

    # Drop columns if they exist
    apollo5_study_report.drop(columns=[col for col in columns_to_drop if col in apollo5_study_report.columns], inplace=True)

    # Preprocess the PatientAge column
    apollo5_study_report['PatientAge_Numeric'] = apollo5_study_report['PatientAge'].apply(preprocess_age)

    # Define the new order of columns
    new_order = ['PatientID', 'Collection', 'Site', 'LongitudinalTemporalEventType', 'LongitudinalTemporalOffsetFromEvent', 'StudyDate', 'StudyInstanceUID', 'StudyDescription', 'SeriesCount', 'ImageCount', 'Unique Modalities', 'PatientAge', 'PatientAge_Numeric', 'PatientSex', 'EthnicGroup']

    # Reorder the columns
    apollo5_study_report = apollo5_study_report.reindex(columns=new_order)

    # save merged report to a CSV
    csv_filename = f"{name}-monthly-report_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    apollo5_study_report.to_csv(csv_filename, index=False)

    return apollo5_study_report, csv_filename, apollo5_series_report, series_csv_filename

def dashboard_filters(df):
    """
    Creates global filters for the dashboard and returns filtered dataframe.
    """
    st.sidebar.header("Dashboard Filters")

    filtered_df = df.copy()

    # Collection Filter
    collections = sorted(df['Collection'].dropna().unique())
    selected_collections = st.sidebar.multiselect("Collection", collections)
    if selected_collections:
        filtered_df = filtered_df[filtered_df['Collection'].isin(selected_collections)]

    # Site Filter
    all_sites = set()
    for s_list in df['Site'].dropna().unique():
        for s in str(s_list).split(', '):
            all_sites.add(s)
    sorted_sites = sorted(list(all_sites))
    selected_sites = st.sidebar.multiselect("Site", sorted_sites)
    if selected_sites:
        mask = filtered_df['Site'].apply(
            lambda x: any(s in str(x).split(', ') for s in selected_sites) if pd.notna(x) else False
        )
        filtered_df = filtered_df[mask]

    # Modality Filter (Multi-select)
    all_modalities = set()
    for m_list in df['Unique Modalities'].dropna().unique():
        for m in m_list.split(', '):
            all_modalities.add(m)
    sorted_modalities = sorted(list(all_modalities))
    selected_modalities = st.sidebar.multiselect("Unique Modalities", sorted_modalities)
    if selected_modalities:
        # Patient matches if ANY of the selected modalities are in their Unique Modalities string
        mask = filtered_df['Unique Modalities'].apply(
            lambda x: any(m in str(x).split(', ') for m in selected_modalities) if pd.notna(x) else False
        )
        filtered_df = filtered_df[mask]

    # Patient Sex Filter
    sexes = sorted(df['PatientSex'].dropna().unique())
    selected_sex = st.sidebar.multiselect("Patient Sex", sexes)
    if selected_sex:
        filtered_df = filtered_df[filtered_df['PatientSex'].isin(selected_sex)]

    # Ethnic Group Filter
    ethnicities = sorted(df['EthnicGroup'].dropna().unique())
    selected_ethnic = st.sidebar.multiselect("Ethnic Group", ethnicities)
    if selected_ethnic:
        filtered_df = filtered_df[filtered_df['EthnicGroup'].isin(selected_ethnic)]

    # Age Filter
    min_age = int(df['PatientAge_Numeric'].min()) if not df['PatientAge_Numeric'].dropna().empty else 0
    max_age = int(df['PatientAge_Numeric'].max()) if not df['PatientAge_Numeric'].dropna().empty else 120
    if min_age > max_age:
        min_age, max_age = max_age, min_age
    selected_age = st.sidebar.slider("Patient Age", min_age, max_age, (min_age, max_age))
    filtered_df = filtered_df[filtered_df['PatientAge_Numeric'].between(selected_age[0], selected_age[1])]

    return filtered_df, selected_collections, selected_sites

def main():

    st.set_page_config(page_title="TCIA APOLLO Reporting", layout="wide")
    st.sidebar.image("https://www.cancerimagingarchive.net/wp-content/uploads/2021/06/TCIA-Logo-01.png")
    st.title("TCIA APOLLO Reporting")

    # Load cached data for dashboard
    latest_report = get_latest_report()
    if latest_report:
        st.info(f"Displaying summary from the latest APOLLO-5 Report: {latest_report}")
        cached_df = pd.read_csv(latest_report)

        # Apply filters
        df_filtered, selected_collections, selected_sites = dashboard_filters(cached_df)

        st.header("APOLLO-5 Summary Dashboard")

        # Overall Totals
        total_patients = df_filtered['PatientID'].nunique()
        total_studies = df_filtered['StudyInstanceUID'].nunique()

        col_total1, col_total2 = st.columns(2)
        with col_total1:
            st.metric("Total Unique Patients", total_patients)
        with col_total2:
            st.metric("Total Unique Studies", total_studies)

        # Summary Table: Count of unique PatientID and StudyInstanceUID by Collection and Site
        summary_table = df_filtered.groupby(['Collection', 'Site']).agg({
            'PatientID': 'nunique',
            'StudyInstanceUID': 'nunique'
        }).reset_index().rename(columns={
            'PatientID': 'Unique Patients',
            'StudyInstanceUID': 'Unique Studies'
        })

        st.subheader("Accrual Summary")
        st.table(summary_table)

        st.subheader("Distributions")

        col_dist1, col_dist2 = st.columns(2)

        with col_dist1:
            # PatientID by PatientSex (Unique Patients)
            sex_counts = df_filtered.drop_duplicates('PatientID')['PatientSex'].value_counts().reset_index()
            sex_counts.columns = ['PatientSex', 'Count']
            fig_sex = px.pie(sex_counts, values='Count', names='PatientSex', title="PatientID by PatientSex")
            st.plotly_chart(fig_sex)

            # PatientID by EthnicGroup (Unique Patients)
            ethnic_counts = df_filtered.drop_duplicates('PatientID')['EthnicGroup'].value_counts().reset_index()
            ethnic_counts.columns = ['EthnicGroup', 'Count']
            fig_ethnic = px.pie(ethnic_counts, values='Count', names='EthnicGroup', title="PatientID by EthnicGroup")
            st.plotly_chart(fig_ethnic)

        with col_dist2:
            # StudyInstanceUID by PatientAge
            # Histogram showing distribution of ages across all studies
            fig_age = px.histogram(df_filtered, x='PatientAge_Numeric',
                                   title="StudyInstanceUID by PatientAge",
                                   labels={'PatientAge_Numeric': 'Patient Age (Years)'})
            st.plotly_chart(fig_age)

            # Distribution of visits per Patient (Unique StudyDates per PatientID)
            visits_per_patient = df_filtered.groupby('PatientID')['StudyDate'].nunique().reset_index()
            visits_per_patient.columns = ['PatientID', 'Unique Study Dates']
            # We want to see how many patients have 1 visit, 2 visits, etc.
            fig_visits = px.histogram(visits_per_patient, x='Unique Study Dates',
                                       title="Distribution of Visits per Patient",
                                       labels={'Unique Study Dates': 'Number of Unique Study Dates'})
            st.plotly_chart(fig_visits)

        st.subheader("Annotation Progress Tracker")
        st.write("Number of unique Study Dates containing the selected modality per patient.")
        modality_to_track = st.radio("Select Modality to Track", ('RTSTRUCT', 'SEG'))

        # Filter for studies containing the selected modality
        mask_mod = df_filtered['Unique Modalities'].apply(
            lambda x: modality_to_track in str(x).split(', ') if pd.notna(x) else False
        )
        mod_filtered = df_filtered[mask_mod]

        # Count unique StudyDates per patient for this modality
        mod_counts = mod_filtered.groupby('PatientID')['StudyDate'].nunique().reset_index()
        mod_counts.columns = ['PatientID', 'Count']

        # We need to include patients who have 0 studies with this modality
        all_patients = pd.DataFrame(df_filtered['PatientID'].unique(), columns=['PatientID'])
        mod_counts = pd.merge(all_patients, mod_counts, on='PatientID', how='left').fillna(0)

        # Categorize into 0, 1, 2+
        def categorize(count):
            if count == 0: return '0 visits'
            if count == 1: return '1 visit'
            return '2+ visits'

        mod_counts['Category'] = mod_counts['Count'].apply(categorize)
        progress_data = mod_counts['Category'].value_counts().reset_index()
        progress_data.columns = ['Category', 'Patient Count']

        # Ensure all categories are represented for consistent plotting
        for cat in ['0 visits', '1 visit', '2+ visits']:
            if cat not in progress_data['Category'].values:
                progress_data = pd.concat([progress_data, pd.DataFrame([{'Category': cat, 'Patient Count': 0}])], ignore_index=True)

        # Sort for better display
        progress_data['sort_idx'] = progress_data['Category'].map({'0 visits': 0, '1 visit': 1, '2+ visits': 2})
        progress_data = progress_data.sort_values('sort_idx')

        fig_progress = px.bar(progress_data, x='Category', y='Patient Count',
                              title=f"Patients with {modality_to_track} Annotations",
                              color='Category',
                              color_discrete_map={'0 visits': 'red', '1 visit': 'orange', '2+ visits': 'green'})
        st.plotly_chart(fig_progress)

        # What Changed section for Dashboard
        latest_series_report = get_latest_report(report_type="series")
        if latest_series_report:
            cached_series_df = pd.read_csv(latest_series_report)
            # Filter series data based on dashboard filters (Collection, Site)
            if selected_collections:
                cached_series_df = cached_series_df[cached_series_df['Collection'].isin(selected_collections)]
            if selected_sites:
                mask_s = cached_series_df['Site'].apply(
                    lambda x: any(s in str(x).split(', ') for s in selected_sites) if pd.notna(x) else False
                )
                cached_series_df = cached_series_df[mask_s]

            display_what_changed(cached_series_df)

    else:
        st.warning("No previous APOLLO-5 reports found. Please generate a report to populate the dashboard.")

    # Sidebar for login
    with st.sidebar:
        st.header("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        # Report selection dropdown
        report_options = ["APOLLO-5 Report", "VAREPOP-APOLLO"]
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

                    if selected_report == "APOLLO-5 Report":
                        with st.spinner("Generating APOLLO-5 Report..."):
                            df, csv_filename, df_series, series_csv_filename = generate_monthly_report("APOLLO-5")
                    if selected_report == "VAREPOP-APOLLO":
                        with st.spinner("Generating VAREPOP-APOLLO Report..."):
                            df, csv_filename, df_series, series_csv_filename = generate_monthly_report("VAREPOP-APOLLO")

                    # Store results in session state to persist after button clicks
                    st.session_state['report_df'] = df
                    st.session_state['report_csv_filename'] = csv_filename
                    st.session_state['report_df_series'] = df_series
                    st.session_state['report_series_csv_filename'] = series_csv_filename
                    st.success("Monthly Report generated successfully!")

                else:
                    st.error("Login failed. Please check your credentials.")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
        else:
            st.warning("Please enter your username and password.")

    # Display results if they exist in session state
    if 'report_df' in st.session_state:
        df = st.session_state['report_df']
        csv_filename = st.session_state['report_csv_filename']
        df_series = st.session_state['report_df_series']
        series_csv_filename = st.session_state['report_series_csv_filename']

        # Display the dataframe
        st.subheader("Monthly Report Data")
        st.dataframe(df)

        # Offer CSV download
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label="Download Study-level CSV",
                data=df.to_csv(index=False),
                file_name=csv_filename,
                mime="text/csv"
            )
        with col_dl2:
            st.download_button(
                label="Download Series-level CSV",
                data=df_series.to_csv(index=False),
                file_name=series_csv_filename,
                mime="text/csv"
            )

        # Visualizations
        st.subheader("Report Summary Stats")
        st.write("Summary statistics for the freshly generated report.")

        col1, col2 = st.columns(2)

        with col1:
            # PatientID by Collection
            patient_counts = df.groupby('Collection')['PatientID'].nunique().reset_index()
            fig_collection = px.pie(patient_counts, values='PatientID', names='Collection',
                                    title="PatientID by Collection")
            st.plotly_chart(fig_collection)

        with col2:
            # Image Count by Collection
            fig_image_count = px.bar(df.groupby('Collection')['ImageCount'].sum().reset_index(),
                                     x='Collection', y='ImageCount', title="Total Image Count by Collection")
            st.plotly_chart(fig_image_count)

        # What Changed section for freshly generated report
        display_what_changed(df_series)

if __name__ == "__main__":
    main()
