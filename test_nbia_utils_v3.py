import nbia_utils as nbia
import pandas as pd
import unittest
from unittest.mock import patch, MagicMock

class TestNBIAUtils(unittest.TestCase):

    @patch('nbia_utils.queryData')
    def test_getSeriesList_column_names(self, mock_query):
        mock_df = pd.DataFrame({
            'Series Instance UID': ['uid1'],
            'Study Instance UID': ['study1'],
            'Image Count': [10]
        })
        mock_query.return_value = mock_df

        result_df = nbia.getSeriesList(['uid1'])
        self.assertIsNotNone(result_df)
        self.assertIn('Study UID', result_df.columns)
        self.assertIn('Number of images', result_df.columns)

if __name__ == '__main__':
    unittest.main()
