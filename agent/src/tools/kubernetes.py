"""
Kubernetes Tools for AutoGen Agents.

This module provides Kubernetes-specific tools that can be registered
with AutoGen agents for function calling.
"""

from __future__ import annotations

import asyncio
from typing import Any, Annotated

import structlog
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from ..config import get_settings

logger = structlog.get_logger()


class KubernetesTools:
    """Kubernetes operations toolkit for AutoGen agents."""

    def __init__(self):
        self.settings = get_settings()
        self._setup_k8s_client()

    def _setup_k8s_client(self):
        """Setup Kubernetes client based on configuration."""
        try:
            if self.settings.kubernetes.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config(config_file=self.settings.kubernetes.kubeconfig)

            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()

            logger.info("Kubernetes client initialized")

        except Exception as e:
            logger.error("Failed to setup K8s client", error=str(e))
            # In test mode, continue without real K8s connection
            if self.settings.development.mock_k8s_api:
                logger.info("Using mock K8s API for testing")
                self.v1 = None
                self.apps_v1 = None
            else:
                raise

    async def get_pod_status(
        self,
        namespace: Annotated[str, "Kubernetes namespace"],
        pod_name: Annotated[str, "Pod name to check"] | None = None,
    ) -> dict[str, Any]:
        """
        Get pod status information.

        Args:
            namespace: Kubernetes namespace
            pod_name: Specific pod name (optional)

        Returns:
            Pod status information
        """
        logger.info("Getting pod status", namespace=namespace, pod=pod_name)

        if self.settings.development.mock_k8s_api:
            return self._mock_pod_status(namespace, pod_name)

        try:
            if pod_name:
                # Get specific pod
                pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
                return self._format_pod_info(pod)
            else:
                # Get all pods in namespace
                pods = self.v1.list_namespaced_pod(namespace=namespace)
                return {
                    "namespace": namespace,
                    "total_pods": len(pods.items),
                    "pods": [
                        self._format_pod_info(pod) for pod in pods.items[:5]
                    ],  # Limit to 5
                }

        except ApiException as e:
            logger.error("K8s API error", error=str(e))
            return {"error": f"Kubernetes API error: {e.reason}"}
        except Exception as e:
            logger.error("Unexpected error", error=str(e))
            return {"error": f"Unexpected error: {str(e)}"}

    async def get_recent_events(
        self,
        namespace: Annotated[str, "Kubernetes namespace"],
        resource_name: Annotated[str, "Resource name"] | None = None,
        limit: Annotated[int, "Max number of events to return"] = 10,
    ) -> dict[str, Any]:
        """
        Get recent Kubernetes events.

        Args:
            namespace: Kubernetes namespace
            resource_name: Filter by resource name (optional)
            limit: Maximum number of events to return

        Returns:
            Recent events information
        """
        logger.info(
            "Getting recent events",
            namespace=namespace,
            resource=resource_name,
            limit=limit,
        )

        if self.settings.development.mock_k8s_api:
            return self._mock_events(namespace, resource_name, limit)

        try:
            events = self.v1.list_namespaced_event(namespace=namespace, limit=limit)

            # Filter by resource if specified
            filtered_events = events.items
            if resource_name:
                filtered_events = [
                    e for e in events.items if e.involved_object.name == resource_name
                ]

            return {
                "namespace": namespace,
                "total_events": len(filtered_events),
                "events": [self._format_event_info(event) for event in filtered_events],
            }

        except ApiException as e:
            logger.error("K8s API error", error=str(e))
            return {"error": f"Kubernetes API error: {e.reason}"}
        except Exception as e:
            logger.error("Unexpected error", error=str(e))
            return {"error": f"Unexpected error: {str(e)}"}

    async def restart_deployment(
        self,
        namespace: Annotated[str, "Kubernetes namespace"],
        deployment_name: Annotated[str, "Deployment name to restart"],
        dry_run: Annotated[bool, "Whether to perform dry run"] = True,
    ) -> dict[str, Any]:
        """
        Restart a Kubernetes deployment.

        Args:
            namespace: Kubernetes namespace
            deployment_name: Deployment to restart
            dry_run: Whether to perform dry run only

        Returns:
            Restart operation result
        """
        logger.info(
            "Restarting deployment",
            namespace=namespace,
            deployment=deployment_name,
            dry_run=dry_run,
        )

        if self.settings.development.mock_k8s_api or dry_run:
            return {
                "operation": "restart_deployment",
                "namespace": namespace,
                "deployment": deployment_name,
                "dry_run": dry_run,
                "status": "success" if not dry_run else "dry_run_success",
                "message": (
                    "Deployment restart completed"
                    if not dry_run
                    else "Dry run: would restart deployment"
                ),
            }

        try:
            # Get current deployment
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            # Add restart annotation to trigger rolling update
            if deployment.spec.template.metadata.annotations is None:
                deployment.spec.template.metadata.annotations = {}

            deployment.spec.template.metadata.annotations[
                "kubectl.kubernetes.io/restartedAt"
            ] = asyncio.get_event_loop().time()

            # Update deployment
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=namespace, body=deployment
            )

            return {
                "operation": "restart_deployment",
                "namespace": namespace,
                "deployment": deployment_name,
                "status": "success",
                "message": "Deployment restart initiated",
            }

        except ApiException as e:
            logger.error("K8s API error", error=str(e))
            return {"error": f"Kubernetes API error: {e.reason}"}
        except Exception as e:
            logger.error("Unexpected error", error=str(e))
            return {"error": f"Unexpected error: {str(e)}"}

    def _format_pod_info(self, pod) -> dict[str, Any]:
        """Format pod information for agent consumption."""
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": pod.status.phase,
            "ready": self._count_ready_containers(pod),
            "restarts": self._count_restarts(pod),
            "created": (
                pod.metadata.creation_timestamp.isoformat()
                if pod.metadata.creation_timestamp
                else None
            ),
        }

    def _format_event_info(self, event) -> dict[str, Any]:
        """Format event information for agent consumption."""
        return {
            "type": event.type,
            "reason": event.reason,
            "message": event.message,
            "object": {
                "kind": event.involved_object.kind,
                "name": event.involved_object.name,
            },
            "first_time": (
                event.first_timestamp.isoformat() if event.first_timestamp else None
            ),
            "last_time": (
                event.last_timestamp.isoformat() if event.last_timestamp else None
            ),
            "count": event.count,
        }

    def _count_ready_containers(self, pod) -> str:
        """Count ready containers in pod."""
        if not pod.status.container_statuses:
            return "0/0"

        ready_count = sum(1 for c in pod.status.container_statuses if c.ready)
        total_count = len(pod.status.container_statuses)
        return f"{ready_count}/{total_count}"

    def _count_restarts(self, pod) -> int:
        """Count total restarts for pod."""
        if not pod.status.container_statuses:
            return 0

        return sum(c.restart_count for c in pod.status.container_statuses)

    def _mock_pod_status(self, namespace: str, pod_name: str | None) -> dict[str, Any]:
        """Mock pod status for testing."""
        if pod_name:
            return {
                "name": pod_name,
                "namespace": namespace,
                "phase": "Running",
                "ready": "1/1",
                "restarts": 0,
                "created": "2025-09-11T10:00:00Z",
            }
        else:
            return {
                "namespace": namespace,
                "total_pods": 2,
                "pods": [
                    {
                        "name": "app-deployment-12345",
                        "namespace": namespace,
                        "phase": "Running",
                        "ready": "1/1",
                        "restarts": 0,
                    },
                    {
                        "name": "app-deployment-67890",
                        "namespace": namespace,
                        "phase": "Pending",
                        "ready": "0/1",
                        "restarts": 1,
                    },
                ],
            }

    def _mock_events(
        self, namespace: str, resource_name: str | None, limit: int
    ) -> dict[str, Any]:
        """Mock events for testing."""
        events = [
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "Unable to mount volumes for pod",
                "object": {"kind": "Pod", "name": resource_name or "test-pod"},
                "count": 3,
            },
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned pod to node",
                "object": {"kind": "Pod", "name": resource_name or "test-pod"},
                "count": 1,
            },
        ]

        return {
            "namespace": namespace,
            "total_events": len(events),
            "events": events[:limit],
        }
