# TikTok publishing stage

The animation renderer produces a vertical MP4 in `tiktok_animator/output/`.

Publishing is intended to use TikTok's official Content Posting API with an authorized app and the `video.publish` scope. The workflow must query creator info, initialize a FILE_UPLOAD post, upload the generated MP4, and verify publish status before considering the run complete.

Required GitHub Actions secrets are an authorized TikTok access token (and refresh credentials if used). Do not commit credentials to the repository.
