import os
import logging
from typing import Optional, List, Dict, Any
from google.cloud import videointelligence

logger = logging.getLogger(__name__)

def annotate_video_gcs(gcs_uri: str) -> Optional[List[Dict[str, Any]]]:
    """Annotates a video file on GCS using Google Cloud Video Intelligence."""
    if os.environ.get("CINESPINE_DISABLE_VIDEO_INTELLIGENCE", "").strip().lower() in ("1", "true", "yes"):
        return None
        
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning("GOOGLE_CLOUD_PROJECT not set, Video Intelligence disabled.")
        return None

    try:
        client = videointelligence.VideoIntelligenceServiceClient()
        
        # We can extract labels, shot changes, and explicit content. 
        # For production verification, shot changes and labels are most useful.
        features = [
            videointelligence.Feature.LABEL_DETECTION,
            videointelligence.Feature.SHOT_CHANGE_DETECTION,
        ]

        logger.info("Starting Video Intelligence annotation for %s", gcs_uri)
        operation = client.annotate_video(
            request={"features": features, "input_uri": gcs_uri}
        )
        
        # This is a long-running operation. In a real system, this would be entirely async.
        # For this demo/worker, we'll wait for the result.
        response = operation.result(timeout=900)
        
        annotations = []
        for result in response.annotation_results:
            result_data = {
                "shot_annotations": [],
                "segment_labels": []
            }
            
            # Process shot changes
            for shot in result.shot_annotations:
                result_data["shot_annotations"].append({
                    "start_time_offset": shot.start_time_offset.total_seconds(),
                    "end_time_offset": shot.end_time_offset.total_seconds()
                })
                
            # Process segment labels (general labels for the whole video/segments)
            for label in result.segment_label_annotations:
                entity = label.entity.description
                segments = []
                for segment in label.segments:
                    segments.append({
                        "confidence": segment.confidence,
                        "start_time_offset": segment.segment.start_time_offset.total_seconds(),
                        "end_time_offset": segment.segment.end_time_offset.total_seconds()
                    })
                result_data["segment_labels"].append({
                    "entity": entity,
                    "segments": segments
                })
                
            annotations.append(result_data)
            
        return annotations
    except Exception as e:
        logger.error("Video Intelligence annotation failed for %s: %s", gcs_uri, e)
        return None
