"""
Improved Prometheus Tools with better query efficiency.

This module provides PrometheusTools that avoid inefficient OR queries
and provide better control over data volume.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
import structlog

from configs.config import get_settings

logger = structlog.get_logger()


class PrometheusTools:
    """Prometheus operations toolkit with efficient querying."""

    def __init__(self, prometheus_url: str | None = None):
        """
        Initialize PrometheusTools.

        Args:
            prometheus_url: Prometheus server URL. If None, will get from settings.
        """
        self.settings = get_settings()

        # Handle placeholder/empty prometheus_url values
        if prometheus_url and isinstance(prometheus_url, str):
            prometheus_url = prometheus_url.strip()
            if prometheus_url.lower() in ["string", "none", "null", ""]:
                prometheus_url = None

        # Get URL from settings, with fallback chain
        if prometheus_url:
            self.prometheus_url = prometheus_url
        else:
            self.prometheus_url = (
                self.settings.monitoring.prometheus_url or "http://localhost:9090"
            )

        self.client = httpx.Client(timeout=30.0)
        logger.info("Prometheus tools initialized", url=self.prometheus_url)

    def _format_datetime(self, dt: datetime) -> str:
        """Convert datetime to Prometheus timestamp format (Unix timestamp)."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return str(int(dt.timestamp()))

    def _parse_datetime_input(self, dt_input: str | datetime | int | float) -> datetime:
        """Parse various datetime input formats to datetime object."""
        if isinstance(dt_input, datetime):
            return dt_input
        elif isinstance(dt_input, str):
            # Handle empty strings, whitespace, or placeholder values
            dt_input = dt_input.strip()
            if not dt_input or dt_input.lower() in ["string", "none", "null", ""]:
                raise ValueError(f"Empty or placeholder datetime value: {dt_input}")

            try:
                # Try ISO format first
                return datetime.fromisoformat(dt_input.replace("Z", "+00:00"))
            except ValueError:
                # Try other common formats
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%H:%M:%S"]:
                    try:
                        parsed = datetime.strptime(dt_input, fmt)
                        if parsed.date() == datetime.now().date() and fmt == "%H:%M:%S":
                            # If only time is provided, use today's date
                            now = datetime.now()
                            parsed = parsed.replace(
                                year=now.year, month=now.month, day=now.day
                            )
                        return parsed.replace(tzinfo=UTC)
                    except ValueError:
                        continue
                raise ValueError(f"Unable to parse datetime: {dt_input}") from None
        elif isinstance(dt_input, (int, float)):
            return datetime.fromtimestamp(dt_input, tz=UTC)
        else:
            raise TypeError(f"Unsupported datetime type: {type(dt_input)}")

    def _is_valid_datetime_value(self, value) -> bool:
        """Check if a datetime value is meaningful and not a placeholder."""
        if value is None:
            return False
        if isinstance(value, str):
            value = value.strip()
            invalid_values = ["string", "none", "null", ""]
            return bool(value) and value.lower() not in invalid_values
        return True

    async def query_multiple_metrics(
        self,
        metric_names: Annotated[
            list[str], "List of specific metric names to query efficiently"
        ],
        start_time: Annotated[
            str | datetime | int | float | None, "Start time for the query. Optional."
        ] = None,
        end_time: Annotated[
            str | datetime | int | float | None, "End time for the query. Optional."
        ] = None,
        namespace: Annotated[
            str | None, "Kubernetes namespace to filter metrics. Optional."
        ] = None,
        pod_name: Annotated[str | None, "Pod name to filter metrics. Optional."] = None,
        limit_per_metric: Annotated[
            int, "Maximum number of time series per metric (default: 50)"
        ] = 50,
        step: Annotated[str, "Query resolution step. Default: '1m'"] = "1m",
    ) -> dict[str, Any]:
        """
        Query multiple specific metrics efficiently (avoids OR queries).

        This executes separate queries for each metric, which is more efficient
        than using OR operators in PromQL.
        """
        try:
            results = {
                "status": "success",
                "query_info": {
                    "namespace_filter": namespace,
                    "pod_name_filter": pod_name,
                    "metrics_requested": len(metric_names),
                    "limit_per_metric": limit_per_metric,
                },
                "metrics_by_name": {},
            }

            # Determine query endpoint based on time range
            endpoint_base = f"{self.prometheus_url}/api/v1/query"
            if start_time is not None or end_time is not None:
                endpoint_base = f"{self.prometheus_url}/api/v1/query_range"

            for metric_name in metric_names:
                try:
                    # Build query for this specific metric with Kubernetes filters
                    filters = []
                    if namespace:
                        filters.append(f'namespace="{namespace}"')
                    if pod_name:
                        filters.append(f'pod=~".*{pod_name}.*"')

                    if filters:
                        filter_str = ",".join(filters)
                        query = f"{metric_name}{{{filter_str}}}"
                    else:
                        query = metric_name

                    # Prepare query parameters
                    params = {"query": query}

                    if start_time is not None or end_time is not None:
                        if (
                            self._is_valid_datetime_value(start_time)
                            and start_time is not None
                        ):
                            start_dt = self._parse_datetime_input(start_time)
                            params["start"] = self._format_datetime(start_dt)
                        else:
                            # Default to 1 hour ago
                            start_dt = datetime.now(UTC) - timedelta(hours=1)
                            params["start"] = self._format_datetime(start_dt)

                        if (
                            self._is_valid_datetime_value(end_time)
                            and end_time is not None
                        ):
                            end_dt = self._parse_datetime_input(end_time)
                            params["end"] = self._format_datetime(end_dt)
                        else:
                            # Default to now
                            end_dt = datetime.now(UTC)
                            params["end"] = self._format_datetime(end_dt)

                        params["step"] = step

                    logger.debug(
                        "Executing metric query",
                        metric_name=metric_name,
                        namespace=namespace,
                        pod_name=pod_name,
                    )

                    # Execute the query
                    response = self.client.get(endpoint_base, params=params)
                    response.raise_for_status()

                    result = response.json()

                    if result.get("status") == "success":
                        data = result.get("data", {})
                        result_type = data.get("resultType")
                        query_results = data.get("result", [])

                        # Apply limit to prevent overwhelming response
                        limited = len(query_results) > limit_per_metric
                        if limited:
                            query_results = query_results[:limit_per_metric]

                        # Format results
                        formatted_results = []
                        for metric in query_results:
                            metric_info = {
                                "metric": metric.get("metric", {}),
                                "values": [],
                            }

                            if result_type == "vector":
                                value = metric.get("value")
                                if value:
                                    metric_info["values"] = [
                                        {"timestamp": value[0], "value": value[1]}
                                    ]
                            elif result_type == "matrix":
                                values = metric.get("values", [])
                                metric_info["values"] = [
                                    {"timestamp": ts, "value": val}
                                    for ts, val in values
                                ]

                            formatted_results.append(metric_info)

                        results["metrics_by_name"][metric_name] = {
                            "query": query,
                            "result_type": result_type,
                            "series_count": len(formatted_results),
                            "limited": limited,
                            "original_count": len(data.get("result", [])),
                            "metrics": formatted_results,
                        }

                    else:
                        error_msg = result.get("error", "Unknown error")
                        results["metrics_by_name"][metric_name] = {
                            "query": query,
                            "error": error_msg,
                        }

                except Exception as e:
                    logger.error(
                        "Error querying metric", metric_name=metric_name, error=str(e)
                    )
                    results["metrics_by_name"][metric_name] = {
                        "query": query,
                        "error": str(e),
                    }

            # Add summary
            successful = len(
                [v for v in results["metrics_by_name"].values() if "error" not in v]
            )
            failed = len(
                [v for v in results["metrics_by_name"].values() if "error" in v]
            )
            total_series = sum(
                v.get("series_count", 0)
                for v in results["metrics_by_name"].values()
                if "series_count" in v
            )

            results["query_info"].update(
                {
                    "successful_metrics": successful,
                    "failed_metrics": failed,
                    "total_series": total_series,
                }
            )

            logger.info(
                "Multiple metrics query completed",
                successful=successful,
                failed=failed,
                total_series=total_series,
            )

            return results

        except Exception as e:
            logger.error("Failed to query multiple metrics", error=str(e))
            return {"status": "error", "error": str(e), "metrics_by_name": {}}

    async def query_essential_metrics(
        self,
        namespace: Annotated[
            str | None, "Kubernetes namespace filter. Optional."
        ] = None,
        pod_name: Annotated[str | None, "Pod name filter. Optional."] = None,
        start_time: Annotated[
            str | datetime | int | float | None, "Start time. Optional."
        ] = None,
        end_time: Annotated[
            str | datetime | int | float | None, "End time. Optional."
        ] = None,
        step: str = "1m",
    ) -> dict[str, Any]:
        """
        Query essential system metrics with calculated values.

        Returns CPU usage percentage, memory usage percentage, disk usage percentage, and system availability—all as calculated metrics rather than raw values.
        """
        try:
            # Define essential calculated metrics with Kubernetes filters
            filters = []
            if namespace:
                filters.append(f'namespace="{namespace}"')
            if pod_name:
                filters.append(f'pod=~".*{pod_name}.*"')

            filter_str = ""
            if filters:
                filter_str = "," + ",".join(filters)

            if namespace or pod_name:
                essential_queries = {
                    "system_up": f"up{{{filter_str[1:]}}}",  # Remove leading comma
                    "cpu_usage_percent": f"100 - (avg by (instance) "
                    f"(rate(node_cpu_seconds_total"
                    f'{{mode="idle"{filter_str}}}[5m])) * 100)',
                    "memory_usage_percent": f"(1 - (node_memory_MemAvailable_bytes"
                    f"{{{filter_str[1:]}}} / "
                    f"node_memory_MemTotal_bytes"
                    f"{{{filter_str[1:]}}})) * 100",
                    "disk_usage_percent": f"(1 - (node_filesystem_free_bytes"
                    f'{{fstype!="tmpfs",fstype!="overlay"'
                    f"{filter_str}}} / "
                    f"node_filesystem_size_bytes"
                    f'{{fstype!="tmpfs",fstype!="overlay"'
                    f"{filter_str}}})) * 100",
                    "load_average": f"node_load1{{{filter_str[1:]}}}",
                }
            else:
                essential_queries = {
                    "system_up": 'up{job="node-exporter"}',
                    "cpu_usage_percent": (
                        "100 - (avg by (instance) "
                        "(rate(node_cpu_seconds_total"
                        '{mode="idle"}[5m])) * 100)'
                    ),
                    "memory_usage_percent": (
                        "(1 - (node_memory_MemAvailable_bytes "
                        "/ node_memory_MemTotal_bytes)) * 100"
                    ),
                    "disk_usage_percent": (
                        "(1 - (node_filesystem_free_bytes"
                        '{fstype!="tmpfs",fstype!="overlay"} '
                        "/ node_filesystem_size_bytes"
                        '{fstype!="tmpfs",fstype!="overlay"})) '
                        "* 100"
                    ),
                    "load_average": "node_load1",
                }

            results = {
                "status": "success",
                "query_info": {
                    "namespace_filter": namespace,
                    "pod_name_filter": pod_name,
                    "essential_metrics_count": len(essential_queries),
                    "description": (
                        "Essential system metrics with " "calculated percentages"
                    ),
                },
                "essential_metrics": {},
            }

            # Determine endpoint
            endpoint_base = f"{self.prometheus_url}/api/v1/query"
            if start_time is not None or end_time is not None:
                endpoint_base = f"{self.prometheus_url}/api/v1/query_range"

            for metric_name, query in essential_queries.items():
                try:
                    # Prepare query parameters
                    params = {"query": query}

                    if start_time is not None or end_time is not None:
                        if (
                            self._is_valid_datetime_value(start_time)
                            and start_time is not None
                        ):
                            start_dt = self._parse_datetime_input(start_time)
                            params["start"] = self._format_datetime(start_dt)
                        else:
                            start_dt = datetime.now(UTC) - timedelta(hours=1)
                            params["start"] = self._format_datetime(start_dt)

                        if (
                            self._is_valid_datetime_value(end_time)
                            and end_time is not None
                        ):
                            end_dt = self._parse_datetime_input(end_time)
                            params["end"] = self._format_datetime(end_dt)
                        else:
                            end_dt = datetime.now(UTC)
                            params["end"] = self._format_datetime(end_dt)

                        params["step"] = step

                    # Execute query
                    response = self.client.get(endpoint_base, params=params)
                    response.raise_for_status()

                    result = response.json()

                    if result.get("status") == "success":
                        data = result.get("data", {})
                        query_results = data.get("result", [])

                        # Keep only top 10 results to avoid overwhelming response
                        if len(query_results) > 10:
                            query_results = query_results[:10]

                        formatted_results = []
                        for metric in query_results:
                            metric_info = {
                                "metric": metric.get("metric", {}),
                                "values": [],
                            }

                            if data.get("resultType") == "vector":
                                value = metric.get("value")
                                if value:
                                    metric_info["values"] = [
                                        {"timestamp": value[0], "value": value[1]}
                                    ]
                            elif data.get("resultType") == "matrix":
                                values = metric.get("values", [])
                                metric_info["values"] = [
                                    {"timestamp": ts, "value": val}
                                    for ts, val in values
                                ]

                            formatted_results.append(metric_info)

                        results["essential_metrics"][metric_name] = {
                            "query": query,
                            "series_count": len(formatted_results),
                            "metrics": formatted_results,
                        }
                    else:
                        results["essential_metrics"][metric_name] = {
                            "query": query,
                            "error": result.get("error", "Unknown error"),
                        }

                except Exception as e:
                    logger.error(
                        "Error querying essential metric",
                        metric_name=metric_name,
                        error=str(e),
                    )
                    results["essential_metrics"][metric_name] = {
                        "query": query,
                        "error": str(e),
                    }

            successful = len(
                [v for v in results["essential_metrics"].values() if "error" not in v]
            )
            failed = len(
                [v for v in results["essential_metrics"].values() if "error" in v]
            )

            results["query_info"]["successful"] = successful
            results["query_info"]["failed"] = failed

            logger.info(
                "Essential metrics query completed",
                successful=successful,
                failed=failed,
            )

            return results

        except Exception as e:
            logger.error("Failed to query essential metrics", error=str(e))
            return {"status": "error", "error": str(e)}

    async def get_metric_names(
        self,
        namespace: Annotated[
            str | None, "Kubernetes namespace to filter metrics. Optional."
        ] = None,
        pod_name: Annotated[str | None, "Pod name to filter metrics. Optional."] = None,
        metric_name: Annotated[
            str | None, "Metric name pattern to filter. Optional."
        ] = None,
        limit: Annotated[
            int, "Maximum number of metric names to return (default: 1000)"
        ] = 1000,
    ) -> dict[str, Any]:
        """
        Get list of available metric names from Prometheus.

        This queries the /api/v1/label/__name__/values endpoint to retrieve
        all available metric names. Optionally filters by namespace, pod,
        and metric name pattern.
        """
        try:
            # Get all metric names from Prometheus
            endpoint = f"{self.prometheus_url}/api/v1/label/__name__/values"
            response = self.client.get(endpoint)
            response.raise_for_status()

            result = response.json()

            if result.get("status") != "success":
                return {
                    "status": "error",
                    "error": result.get("error", "Failed to get metric names"),
                }

            all_metrics = result.get("data", [])

            # Apply metric name pattern filter first (client-side filtering)
            if metric_name:
                import re

                pattern = metric_name.replace("*", ".*").replace("?", ".")
                regex = re.compile(pattern, re.IGNORECASE)
                all_metrics = [m for m in all_metrics if regex.search(m)]

            # If no filters are specified, return all metrics (limited)
            if not namespace and not pod_name:
                limited_metrics = (
                    all_metrics[:limit] if len(all_metrics) > limit else all_metrics
                )

                return {
                    "status": "success",
                    "total_metrics": len(all_metrics),
                    "returned_metrics": len(limited_metrics),
                    "limited": len(all_metrics) > limit,
                    "namespace_filter": None,
                    "pod_name_filter": None,
                    "metric_name_filter": metric_name,
                    "metrics": limited_metrics,
                }

            # If filters are specified, we need to check which metrics actually exist
            # with those filters by testing each metric
            filtered_metrics = []

            # Build filter query parts
            filters = []
            if namespace:
                filters.append(f'namespace="{namespace}"')
            if pod_name:
                filters.append(f'pod=~".*{pod_name}.*"')

            filter_str = ",".join(filters)

            # Test a sample of metrics to see which ones have data with filters
            test_metrics = all_metrics[: min(100, len(all_metrics))]  # Test first 100

            for metric_name in test_metrics:
                try:
                    # Quick test query to see if this metric exists with filters
                    test_query = f"{metric_name}{{{filter_str}}}"
                    test_params = {"query": test_query}

                    test_response = self.client.get(
                        f"{self.prometheus_url}/api/v1/query", params=test_params
                    )
                    test_response.raise_for_status()

                    test_result = test_response.json()
                    if test_result.get("status") == "success" and test_result.get(
                        "data", {}
                    ).get("result"):
                        filtered_metrics.append(metric_name)

                        # Stop if we've found enough metrics
                        if len(filtered_metrics) >= limit:
                            break

                except Exception:
                    # If individual metric test fails, skip it
                    continue

            return {
                "status": "success",
                "total_metrics_tested": len(test_metrics),
                "filtered_metrics": len(filtered_metrics),
                "namespace_filter": namespace,
                "pod_name_filter": pod_name,
                "metric_name_filter": metric_name,
                "metrics": filtered_metrics,
                "note": (
                    "Filtered results based on metrics that have data "
                    f"matching the specified filters. Tested {len(test_metrics)} "
                    f"out of {len(all_metrics)} total available metrics."
                ),
            }

        except Exception as e:
            logger.error("Failed to get metric names", error=str(e))
            return {"status": "error", "error": str(e)}

    async def get_targets(self) -> dict[str, Any]:
        """
        Get information about Prometheus targets (scraped endpoints).

        This method queries the Prometheus /api/v1/targets endpoint to retrieve
        information about all targets being scraped by Prometheus, including
        their health status, discovery labels, and scrape information.

        Returns:
            Dictionary containing targets information with status and details.
        """
        try:
            logger.info("Querying Prometheus targets")

            response = self.client.get(f"{self.prometheus_url}/api/v1/targets")
            response.raise_for_status()

            result = response.json()

            if result.get("status") != "success":
                return {
                    "status": "error",
                    "error": result.get("error", "Failed to get targets"),
                }

            targets_data = result.get("data", {})
            active_targets = targets_data.get("activeTargets", [])
            dropped_targets = targets_data.get("droppedTargets", [])

            # Count targets by health status
            healthy_targets = sum(
                1 for target in active_targets if target.get("health") == "up"
            )
            unhealthy_targets = sum(
                1 for target in active_targets if target.get("health") == "down"
            )

            # Organize active targets by job
            targets_by_job = {}
            for target in active_targets:
                job_name = target.get("labels", {}).get("job", "unknown")
                if job_name not in targets_by_job:
                    targets_by_job[job_name] = []

                # Extract useful target information
                target_info = {
                    "instance": target.get("labels", {}).get("instance", "unknown"),
                    "health": target.get("health", "unknown"),
                    "scrape_url": target.get("scrapeUrl", ""),
                    "last_scrape": target.get("lastScrape", ""),
                    "scrape_duration": target.get("scrapeDuration", ""),
                    "last_error": target.get("lastError", ""),
                    "labels": target.get("labels", {}),
                }
                targets_by_job[job_name].append(target_info)

            return {
                "status": "success",
                "summary": {
                    "total_active_targets": len(active_targets),
                    "total_dropped_targets": len(dropped_targets),
                    "healthy_targets": healthy_targets,
                    "unhealthy_targets": unhealthy_targets,
                    "jobs_count": len(targets_by_job),
                },
                "targets_by_job": targets_by_job,
                "prometheus_url": self.prometheus_url,
                "query_timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to get targets", error=str(e))
            return {"status": "error", "error": str(e)}

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "client"):
            self.client.close()
