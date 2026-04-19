import requests
from datetime import datetime
from config import config


class AirflowService:

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _auth(self):
        return (config.AIRFLOW_USERNAME, config.AIRFLOW_PASSWORD)

    def trigger_pipeline(self, steam_id: str) -> str:
        """
        game_pipeline DAG를 steam_id를 conf로 전달하며 트리거.
        반환값: dag_run_id (상태 폴링에 사용)
        """
        run_id = f"flask_{steam_id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
        url = f"{config.AIRFLOW_BASE_URL}/api/v1/dags/{config.AIRFLOW_DAG_ID}/dagRuns"
        payload = {
            "dag_run_id": run_id,
            "conf": {"steam_id": steam_id},
        }
        try:
            resp = requests.post(
                url, json=payload, auth=self._auth(),
                headers=self._headers(), timeout=10
            )
            resp.raise_for_status()
            return resp.json().get("dag_run_id", run_id)
        except requests.RequestException as e:
            raise RuntimeError(f"Airflow DAG 트리거 실패: {e}")

    def get_run_status(self, dag_run_id: str) -> str:
        """
        DAG 실행 상태 조회.
        반환값: 'queued' | 'running' | 'success' | 'failed'
        """
        url = (
            f"{config.AIRFLOW_BASE_URL}/api/v1/dags"
            f"/{config.AIRFLOW_DAG_ID}/dagRuns/{dag_run_id}"
        )
        try:
            resp = requests.get(url, auth=self._auth(), timeout=10)
            resp.raise_for_status()
            return resp.json().get("state", "unknown")
        except requests.RequestException as e:
            raise RuntimeError(f"Airflow 상태 조회 실패: {e}")


airflow_svc = AirflowService()
