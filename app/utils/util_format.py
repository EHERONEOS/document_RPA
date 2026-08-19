from urllib.parse import parse_qs

def format_post_data(postData:str):
    """格式化postData"""
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(postData).items()}
        