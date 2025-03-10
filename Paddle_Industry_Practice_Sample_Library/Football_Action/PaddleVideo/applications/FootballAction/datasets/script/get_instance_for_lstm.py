"""
get instance for lstm
根据gts计算每个proposal_bmn的iou、ioa、label等信息
"""
import os
import sys
import json
import random
import pickle
import numpy as np

dataset = "/home/PaddleVideo/applications/FootballAction/datasets/EuroCup2016"
feat_dir = dataset + '/features'
prop_file = dataset + '/feature_bmn/prop.json'
out_dir = dataset + '/input_for_lstm'
label_files = {
    'train': 'label_cls8_train.json',
    'validation': 'label_cls8_val.json'
}


def IoU(e1, e2):
    """
    clc iou and ioa
    """
    area1 = e1["end"] - e1["start"]
    area2 = e2["end"] - e2["start"]
    x1 = np.maximum(e1["start"], e2["start"])
    x2 = np.minimum(e1["end"], e2["end"])
    inter = np.maximum(0.0, x2 - x1)
    iou = 0.0 if (area1 + area2 -
                  inter) == 0 else inter * 1.0 / (area1 + area2 - inter)
    ioa = 0.0 if area2 == 0 else inter * 1.0 / area2
    return iou, ioa


def clc_iou_of_proposal(proposal, gts):
    hit_gts = {}
    label = 0
    norm_start = 0.
    hit = False
    for gt in gts:
        e1 = {'start': proposal['start'], 'end': proposal['end']}
        e2 = {'start': gt['start_id'], 'end': gt['end_id']}
        iou, ioa = IoU(e1, e2)
        if iou > 0:
            hit = True
            hit_gts = gt
            label = hit_gts['label_ids'][0]
            norm_start = (gt['start_id'] - proposal['start']) * 1.0 / (
                proposal['end'] - proposal['start'])
            break
    res = {
        'label': label,
        'norm_iou': iou,
        'norm_ioa': ioa,
        'norm_start': norm_start,
        'proposal': proposal,
        'hit_gts': hit_gts
    }
    return res


def get_bmn_info(gts_data, proposal_data, res_bmn, mode, score_threshold=0.01):
    """
    @param, gts_data, original gts for action detection
    @param, proposal_data, proposal actions from bmn
    @param, mode, train or validation
    @return, None.
    """
    fps = gts_data['fps']
    res_bmn['fps'] = fps
    for gts_item in gts_data['gts']:
        url = gts_item['url']
        print(url)
        max_length = gts_item['total_frames']

        video_name = os.path.basename(url).split('.')[0]
        if not video_name in proposal_data:
            continue

        gts_actions = gts_item['actions']
        prop_actions = proposal_data[video_name]

        res_bmn['results'].append({
            'url': url,
            'mode': mode,
            'total_frames': max_length,
            'num_gts': len(gts_actions),
            'num_proposals': len(prop_actions),
            'proposal_actions': []
        })
        for proposal in prop_actions:
            if proposal['score'] < score_threshold:
                continue
            proposal['start'] = int(proposal['start'] * 1.0 / fps)
            proposal['end'] = int(proposal['end'] * 1.0 / fps)
            gts_info = clc_iou_of_proposal(proposal, gts_actions)
            res_bmn['results'][-1]['proposal_actions'].append(gts_info)

    return res_bmn


def save_feature(label_info, out_dir):
    print('save feature ...')
    fps = label_info['fps']
    out_feature_dir = out_dir + '/feature'
    if not os.path.exists(out_feature_dir):
        os.mkdir(out_feature_dir)
    fid_train = open(out_dir + '/train.txt', 'w')
    fid_val = open(out_dir + '/val.txt', 'w')
    for res in label_info['results']:
        basename = os.path.basename(res['url']).split('.')[0]
        print(basename, res['num_proposals'])
        mode = res['mode']
        fid = fid_train if mode == 'train' else fid_val
        feature_path = os.path.join(feat_dir, basename + '.pkl')
        feature_data = pickle.load(open(feature_path, 'rb'))
        image_feature = feature_data['image_feature']
        audio_feature = feature_data['audio_feature']
        max_len_audio = len(audio_feature)
        for proposal in res['proposal_actions']:
            label = proposal['label']
            start_id = proposal['proposal']['start']
            end_id = proposal['proposal']['end']
            # get hit feature
            image_feature_hit = image_feature[start_id * fps:end_id * fps]
            audio_feature_hit = audio_feature[min(start_id, max_len_audio
                                                  ):min(end_id, max_len_audio)]

            # save
            anno_info = {
                'image_feature': np.array(image_feature_hit, dtype=np.float32),
                'audio_feature': np.array(audio_feature_hit, dtype=np.float32),
                'feature_fps': fps,
                'label_info': proposal,
                'video_name': basename
            }
            save_name = '{}/{}_{}_{}.pkl'.format(out_feature_dir, basename,
                                                 start_id, end_id)
            with open(save_name, 'wb') as f:
                pickle.dump(anno_info, f, protocol=pickle.HIGHEST_PROTOCOL)
            fid.write('{} {}\n'.format(save_name, label))

    fid_train.close()
    fid_val.close()
    print('done!')


if __name__ == "__main__":
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)
    prop_data = json.load(open(prop_file, 'rb'))
    proposal_data = {}
    for item in prop_data:
        proposal_data[os.path.basename(
            item['video_name'])] = item['bmn_results']

    # get label info
    res_bmn = {'fps': 0, 'results': []}
    for item, value in label_files.items():
        label_file = os.path.join(dataset, value)
        gts_data = json.load(open(label_file, 'rb'))
        res_bmn = get_bmn_info(gts_data, proposal_data, res_bmn, item)

    with open(out_dir + '/label_info.json', 'w', encoding='utf-8') as f:
        data = json.dumps(res_bmn, indent=4, ensure_ascii=False)
        f.write(data)

    # save feature
    save_feature(res_bmn, out_dir)
