import itertools
import json
from collections import Counter
from time import sleep

import MeCab
import httplib2
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from websocket import create_connection

credentials_path = "credentials.json"
store = Storage(credentials_path)
credentials = store.get()

if credentials is None or credentials.invalid:
    f = "client.json"
    scope = "https://www.googleapis.com/auth/youtube.readonly"
    flow = client.flow_from_clientsecrets(f, scope)
    flow.user_agent = "aaa"
    credentials = tools.run_flow(flow, Storage(credentials_path))

http = credentials.authorize(httplib2.Http())


def check_live_streaming(channel_id: str):
    url = "https://www.googleapis.com/youtube/v3/search?part=id&eventType=live&type=video&channelId="
    url += channel_id
    res, data = http.request(url)
    data = json.loads(data.decode())
    return "items" in data.keys() and len(data["items"]) > 0


def get_chat_id(video_id: str):
    url = "https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id="
    url += video_id
    res, data = http.request(url)
    data = json.loads(data.decode())

    chat_id = data["items"][0]['liveStreamingDetails']["activeLiveChatId"]
    return chat_id


def get_live_video_id(channel_id: str):
    url = "https://www.googleapis.com/youtube/v3/search?part=snippet&eventType=live&type=video&channelId="
    url += channel_id
    res, data = http.request(url)
    data = json.loads(data.decode())
    if len(data["items"]) == 0:
        return None
    return data["items"][0]["id"]["videoId"]


def get_chat_texts(chat_id: str):
    url = "https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet,authorDetails"
    url += "&liveChatId=" + chat_id

    ret = []

    res, data = http.request(url)
    data = json.loads(data.decode())
    if "items" in data.keys():
        for item in data["items"]:
            # スパチャ避け
            if "textMessageDetails" in item["snippet"].keys():
                ret.append(item["snippet"]["textMessageDetails"]["messageText"])
    return ret


def get_channel_banner_url(channel_id: str):
    url = "https://www.googleapis.com/youtube/v3/channels?part=brandingSettings&id="
    url += channel_id
    res, data = http.request(url)
    data = json.loads(data.decode())

    return data["items"][0]["brandingSettings"]["image"]["bannerImageUrl"]


def get_thumbnail_url(video_id: str):
    url = "https://www.googleapis.com/youtube/v3/videos?part=snippet&id="
    url += video_id
    res, data = http.request(url)
    data = json.loads(data.decode())
    return data["items"][0]["snippet"]["thumbnails"]["standard"]["url"]


def get_nouns(lines: list):
    ret = []
    for s in lines:
        tagger.parse('')
        m = tagger.parseToNode(s)
        while m:
            if m.feature.split(',')[0] == '名詞':
                ret.append(m.surface)
            m = m.next
    return ret


def get_active_channels(channel_ids: list):
    ret = itertools.islice(
        ((channel_id,
          get_live_video_id(channel_id),
          name)
         for channel_id, name in channel_ids
         if check_live_streaming(channel_id)), 100)

    return [(channel_id,
             get_chat_id(live_video_id),
             get_thumbnail_url(live_video_id),
             name)
            for channel_id, live_video_id, name in ret
            if live_video_id is not None]


with open("list.csv", encoding="utf8", mode='r') as f:
    channel_ids = [(ll[1], ll[2])
                   for ll in (l.strip().split(",") for l in f)
                   if len(ll) == 6][1:]

ws = create_connection("ws://localhost:8080/websocket")
# tagger = MeCab.Tagger('-d /usr/local/lib/mecab/dic/mecab-ipadic-neologd')
tagger = MeCab.Tagger('-d /usr/lib/mecab/dic/mecab-ipadic-neologd')

active_channels = get_active_channels(channel_ids)

t = 0
while True:
    if t % 36 == 0:
        active_channels = get_active_channels(channel_ids)
    for channel_id, chat_id, thumbnail_url, name in reversed(active_channels):
        texts = get_chat_texts(chat_id)
        nouns = get_nouns(texts)
        json_str = json.dumps({
            "channel_id": channel_id,
            "name": name,
            "thumbnail_url": thumbnail_url,
            "texts": texts,
            "nouns": Counter(nouns).most_common(25)
        }, ensure_ascii=False)
        ws.send(json_str)
        # print(json_str)
    sleep(5)
    t += 1
