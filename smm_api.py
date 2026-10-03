import os
class SMMProvider:
    def __init__(self): self.base_url=os.getenv('SMM_API_URL',''); self.api_key=os.getenv('SMM_API_KEY','')
    def configured(self): return bool(self.base_url and self.api_key)
