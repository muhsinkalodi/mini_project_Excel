import sys
from dataclasses import dataclass
import numpy as np
import pandas as pd
import os

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.exception import CustomException
from src.logger import logging
from src.utils import save_object

@dataclass
class DataTransformationConfig:
    preprocessor_obj_file_path = os.path.join('artifacts', 'preprocessor.pkl')

class DataTransformation:
    def __init__(self):
        self.data_transformation_config = DataTransformationConfig()

    def get_data_transformer_object(self):
        try:
            # All input columns are numerical
            numerical_columns = [
                'Math_Internal1', 'Math_Internal2', 'Math_Internal3',
                'Physics_Internal1', 'Physics_Internal2', 'Physics_Internal3',
                'Chemistry_Internal1', 'Chemistry_Internal2', 'Chemistry_Internal3',
                'CS_Internal1', 'CS_Internal2', 'CS_Internal3',
                'English_Internal1', 'English_Internal2', 'English_Internal3',
                'Aptitude_Internal1', 'Aptitude_Internal2', 'Aptitude_Internal3'
            ]

            num_pipeline = Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", StandardScaler())
                ]
            )

            preprocessor = ColumnTransformer(
                transformers=[
                    ("num_pipeline", num_pipeline, numerical_columns)
                ]
            )

            logging.info("Numerical pipeline created for internal marks preprocessing.")
            return preprocessor

        except Exception as e:
            raise CustomException(e, sys)

    def initiate_data_transformation(self, train_path, test_path):
        try:
            train_df = pd.read_csv(train_path)
            test_df = pd.read_csv(test_path)

            logging.info("Train and test data read successfully.")

            preprocessing_obj = self.get_data_transformer_object()

            # Multi-output targets: all semester marks
            target_columns = [
                    "Math_Semester", "Physics_Semester", "Chemistry_Semester",
                    "CS_Semester", "English_Semester", "Aptitude_Semester"
                ]


            input_features_train_df = train_df.drop(columns=target_columns + ["Performance_Class"], axis=1)
            target_feature_train_df = train_df[target_columns]

            input_features_test_df = test_df.drop(columns=target_columns + ["Performance_Class"], axis=1)
            target_feature_test_df = test_df[target_columns]

            logging.info("Applying preprocessing on train and test input features.")

            input_feature_train_arr = preprocessing_obj.fit_transform(input_features_train_df)
            input_feature_test_arr = preprocessing_obj.transform(input_features_test_df)

            train_arr = np.c_[input_feature_train_arr, np.array(target_feature_train_df)]
            test_arr = np.c_[input_feature_test_arr, np.array(target_feature_test_df)]

            logging.info("Saving preprocessor object to artifacts.")
            save_object(
                file_path=self.data_transformation_config.preprocessor_obj_file_path,
                obj=preprocessing_obj
            )

            return train_arr, test_arr

        except Exception as e:
            raise CustomException(e, sys)
