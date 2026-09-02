from models.predict import PredictRequest

class ModerationService:
    def predict(self, req: PredictRequest) -> bool:
        """
        True есть нарушение
        False нарушений нет
        """

        if req.is_verified_seller:
            return False

        if req.images_qty > 0:
            return False

        return True