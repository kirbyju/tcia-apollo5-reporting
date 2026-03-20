import nbia_utils as nbia
import pandas as pd
import unittest
from unittest.mock import patch, MagicMock

class TestNBIAUtils(unittest.TestCase):

    @patch('nbia_utils.queryData')
    def test_getStudy_returns_original_keys(self, mock_query):
        mock_data = [
            {
                "StudyInstanceUID": "uid1",
                "ImageCount": 10
            }
        ]
        mock_query.return_value = mock_data

        result = nbia.getStudy(collection="TEST")
        self.assertEqual(result[0]['StudyInstanceUID'], "uid1")
        self.assertIn('ImageCount', result[0])

    @patch('nbia_utils.queryData')
    def test_getSeriesList_standardizes_columns(self, mock_query):
        mock_df = pd.DataFrame({
            'Study Instance UID': ['uid1'],
            'Image Count': [10]
        })
        mock_query.return_value = mock_df

        result_df = nbia.getSeriesList(['uid1'])
        self.assertIn('Study UID', result_df.columns)
        self.assertIn('Number of images', result_df.columns)

if __name__ == '__main__':
    unittest.main()
