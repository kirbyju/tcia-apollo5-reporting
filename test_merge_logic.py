import pandas as pd
from tcia_utils import nbia
import datetime
import os

def test_generate_report():
    # This is a dummy test to see if the code runs without syntax errors
    # and to check what columns are produced if we can mock the API calls
    # Since I don't have real credentials, I'll just check if the logic for merging works

    series_info = pd.DataFrame({
        'Series Instance UID': ['s1', 's2'],
        'Study UID': ['st1', 'st1'],
        'Modality': ['CT', 'RTSTRUCT'],
        'Number of images': [100, 1]
    })

    series_site_info = pd.DataFrame({
        'series': ['s1', 's2'],
        'collectionSite': ['Coll1//Site1', 'Coll1//Site1'],
        'StudyInstanceUID': ['st1', 'st1']
    })

    studies = pd.DataFrame({
        'PatientID': ['p1'],
        'Collection': ['Coll1'],
        'StudyInstanceUID': ['st1'],
        'StudyDate': ['2023-01-01'],
        'SeriesCount': [2],
        'PatientAge': ['50Y'],
        'PatientSex': ['M'],
        'EthnicGroup': ['E1']
    })

    # Mocking the part of generate_monthly_report
    series_report_site_info = series_site_info.copy()
    series_report_site_info[['Collection', 'Site']] = series_report_site_info['collectionSite'].str.split('//', expand=True)

    series_uid_col = 'Series Instance UID' if 'Series Instance UID' in series_info.columns else ('SeriesInstanceUID' if 'SeriesInstanceUID' in series_info.columns else None)

    if series_uid_col:
        apollo5_series_report = pd.merge(
            series_info,
            series_report_site_info[['series', 'Collection', 'Site']],
            left_on=series_uid_col,
            right_on='series',
            how='left'
        )
        if 'series' in apollo5_series_report.columns and series_uid_col != 'series':
            apollo5_series_report.drop(columns=['series'], inplace=True)
    else:
        apollo5_series_report = series_info.copy()

    print("Series Report Columns:", apollo5_series_report.columns.tolist())
    print(apollo5_series_report)

if __name__ == "__main__":
    test_generate_report()
