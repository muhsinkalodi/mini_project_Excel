import sys
import pandas as pd
from src.exception import CustomException
from src.utils import load_object
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,  # Set the logging level
                    format="%(asctime)s - %(levelname)s - %(message)s")


class PredictPipeline:
    def __init__(self, artifact_dir="artifacts"):
        """
        Initializes the PredictPipeline.

        Args:
            artifact_dir (str, optional): The directory where artifacts are stored.
                Defaults to "artifacts".
        """
        self.artifact_dir = artifact_dir

    def predict(self, features):
        """
        Predicts using the loaded model and preprocessor.

        Args:
            features (pd.DataFrame): The input features as a Pandas DataFrame.

        Returns:
            numpy.ndarray: The predictions.

        Raises:
            CustomException: If an error occurs during prediction.
        """
        try:
            cwd = os.getcwd()  # Get current working directory once
            model_path = os.path.join(cwd, self.artifact_dir, 'model.pkl')
            preprocessor_path = os.path.join(cwd, self.artifact_dir, 'preprocessor.pkl')

            model = load_object(file_path=model_path)
            preprocessor = load_object(file_path=preprocessor_path)

            data_scaled = preprocessor.transform(features)
            predictions = model.predict(data_scaled)  # Changed to predictions

            logging.info("Prediction successful.")
            return predictions
        except Exception as e:
            error_message = f"Error in PredictPipeline.predict: {e}\n{traceback.format_exc()}"
            logging.error(error_message)
            raise CustomException(error_message, sys)


class CustomData:
    def __init__(self,
                 math_internal1: float, math_internal2: float, math_internal3: float,
                 physics_internal1: float, physics_internal2: float, physics_internal3: float,
                 chemistry_internal1: float, chemistry_internal2: float, chemistry_internal3: float,
                 cs_internal1: float, cs_internal2: float, cs_internal3: float,
                 english_internal1: float, english_internal2: float, english_internal3: float,
                 aptitude_internal1: float, aptitude_internal2: float, aptitude_internal3: float
                 ):
        """
        Initializes the CustomData object.

        Args:
            ... (all the internal marks)
        """
        self.math_internal1 = math_internal1
        self.math_internal2 = math_internal2
        self.math_internal3 = math_internal3
        self.physics_internal1 = physics_internal1
        self.physics_internal2 = physics_internal2
        self.physics_internal3 = physics_internal3
        self.chemistry_internal1 = chemistry_internal1
        self.chemistry_internal2 = chemistry_internal2
        self.chemistry_internal3 = chemistry_internal3
        self.cs_internal1 = cs_internal1
        self.cs_internal2 = cs_internal2
        self.cs_internal3 = cs_internal3
        self.english_internal1 = english_internal1
        self.english_internal2 = english_internal2
        self.english_internal3 = english_internal3
        self.aptitude_internal1 = aptitude_internal1
        self.aptitude_internal2 = aptitude_internal2
        self.aptitude_internal3 = aptitude_internal3

    def get_data_as_dataframe(self):
        """
        Converts the data to a Pandas DataFrame.

        Returns:
            pd.DataFrame: The data as a Pandas DataFrame.

        Raises:
            CustomException: If an error occurs during DataFrame creation.
        """
        try:
            data_dict = {
                "Math_Internal1": [self.math_internal1],
                "Math_Internal2": [self.math_internal2],
                "Math_Internal3": [self.math_internal3],
                "Physics_Internal1": [self.physics_internal1],
                "Physics_Internal2": [self.physics_internal2],
                "Physics_Internal3": [self.physics_internal3],
                "Chemistry_Internal1": [self.chemistry_internal1],
                "Chemistry_Internal2": [self.chemistry_internal2],
                "Chemistry_Internal3": [self.chemistry_internal3],
                "CS_Internal1": [self.cs_internal1],
                "CS_Internal2": [self.cs_internal2],
                "CS_Internal3": [self.cs_internal3],
                "English_Internal1": [self.english_internal1],
                "English_Internal2": [self.english_internal2],
                "English_Internal3": [self.english_internal3],
                "Aptitude_Internal1": [self.aptitude_internal1],
                "Aptitude_Internal2": [self.aptitude_internal2],
                "Aptitude_Internal3": [self.aptitude_internal3],
            }
            logging.info("DataFrame creation successful.")
            return pd.DataFrame(data_dict)
        except Exception as e:
            error_message = f"Error in CustomData.get_data_as_dataframe: {e}\n{traceback.format_exc()}"
            logging.error(error_message)
            raise CustomException(error_message, sys)