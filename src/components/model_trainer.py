import os
import sys
from dataclasses import dataclass

from sklearn.multioutput import MultiOutputRegressor
from sklearn.ensemble import (
    RandomForestRegressor,
    GradientBoostingRegressor,
    AdaBoostRegressor,
)
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.tree import DecisionTreeRegressor
from xgboost import XGBRegressor
from catboost import CatBoostRegressor
from sklearn.metrics import r2_score

from src.exception import CustomException
from src.logger import logging
from src.utils import save_object, evaluate_model_multi


@dataclass
class ModelTrainerConfig:
    trained_model_file_path = os.path.join('artifacts', 'model.pkl')


class ModelTrainer:
    def __init__(self):
        self.model_trainer_config = ModelTrainerConfig()

    def initiate_model_trainer(self, train_array, test_array):
        try:
            logging.info("Splitting training and test data")

            # ✅ Now handle multi-output (e.g., 6 subjects)
            x_train, y_train = train_array[:, :-6], train_array[:, -6:]
            x_test, y_test = test_array[:, :-6], test_array[:, -6:]

            base_models = {
                "Random Forest": RandomForestRegressor(),
                "Gradient Boosting": GradientBoostingRegressor(),
                "Ada Boost": AdaBoostRegressor(),
                "Decision Tree": DecisionTreeRegressor(),
                "Linear Regression": LinearRegression(),
                "KNeighbors": KNeighborsRegressor(),
                "XGBoost": XGBRegressor(),
                "CatBoost": CatBoostRegressor(verbose=0)
            }

            wrapped_models = {
                name: MultiOutputRegressor(model)
                for name, model in base_models.items()
            }

            print("\n📊 Evaluating Multi-Output Models...\n")
            model_report = evaluate_model_multi(
                x_train=x_train, y_train=y_train,
                x_test=x_test, y_test=y_test,
                models=wrapped_models
            )

            for model_name, score in model_report.items():
                print(f"✅ {model_name} Average R² Score: {score:.4f}")

            best_model_name = max(model_report, key=model_report.get)
            best_model = wrapped_models[best_model_name]
            best_score = model_report[best_model_name]

            print(f"\n🏆 Best Model: {best_model_name} with Average R² Score: {best_score:.4f}")

            if best_score < 0.4:
                raise CustomException("No suitable model found with R² >= 0.4", sys)

            logging.info(f"Saving best multi-output model: {best_model_name}")
            save_object(
                file_path=self.model_trainer_config.trained_model_file_path,
                obj=best_model
            )

            predictions = best_model.predict(x_test)
            r2_scores = [
                r2_score(y_test[:, i], predictions[:, i])
                for i in range(y_test.shape[1])
            ]
            avg_r2 = sum(r2_scores) / len(r2_scores)

            print(f"\n📈 Final Test Average R² Score: {avg_r2:.4f}")
            return avg_r2

        except Exception as e:
            raise CustomException(e, sys)
