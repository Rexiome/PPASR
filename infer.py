import argparse
import functools
import time

import paddle

from data_utils.audio_process import AudioProcess
from utils.utils import add_arguments, print_arguments
from decoders.ctc_greedy_decoder import greedy_decoder

parser = argparse.ArgumentParser(description=__doc__)
add_arg = functools.partial(add_arguments, argparser=parser)
add_arg('alpha',            float,  1.2,                      '集束搜索的LM系数')
add_arg('beta',             float,  0.35,                     '集束搜索的WC系数')
add_arg('beam_size',        int,    10,                       '集束搜索的大小，范围:[5, 500]')
add_arg('num_proc_bsearch', int,    8,                        '集束搜索方法使用CPU数量')
add_arg('cutoff_prob',      float,  1.0,                      '剪枝的概率')
add_arg('cutoff_top_n',     int,    40,                       '剪枝的最大值')
add_arg('audio_path',       str,   'dataset/test.wav',        '用于识别的音频路径')
add_arg('dataset_vocab',    str,   'dataset/vocabulary.txt',  '数据字典的路径')
add_arg('model_path',       str,   'models/infer/model',      '模型的路径')
add_arg('mean_std_path',    str,   'dataset/mean_std.npz',    '数据集的均值和标准值的npy文件路径')
add_arg('decoder',          str,   'ctc_greedy',         '结果解码方法', choices=['ctc_beam_search', 'ctc_greedy'])
add_arg('lang_model_path',  str,   'lm/zh_giga.no_cna_cmn.prune01244.klm',        "语言模型文件路径")
args = parser.parse_args()


print_arguments(args)
# 加载数据字典
vocab_lines = []
with open(args.dataset_vocab, 'r', encoding='utf-8') as file:
    vocab_lines.extend(file.readlines())
vocab_list = [line.replace('\n', '') for line in vocab_lines]

# 提取音频特征器和归一化器
audio_process = AudioProcess(mean_std_filepath=args.mean_std_path)

# 创建模型
model = paddle.jit.load(args.model_path)
model.eval()


# 集束搜索方法的处理
if args.decoder == "ctc_beam_search":
    try:
        from decoders.beam_search_decoder import BeamSearchDecoder
        beam_search_decoder = BeamSearchDecoder(args.alpha, args.beta, args.lang_model_path, vocab_list)
    except ModuleNotFoundError:
        raise Exception('缺少ctc_decoders库，请在decoders目录中安装ctc_decoders库，如果是Windows系统，请使用ctc_greed。')


# 执行解码
def decoder(out, vocab):
    if args.decoder == 'ctc_greedy':
        result = greedy_decoder(out, vocab)
    else:
        result = beam_search_decoder.decode_beam_search(probs_split=out,
                                                        beam_alpha=args.alpha,
                                                        beam_beta=args.beta,
                                                        beam_size=args.beam_size,
                                                        cutoff_prob=args.cutoff_prob,
                                                        cutoff_top_n=args.cutoff_top_n,
                                                        vocab_list=vocab)
    score, text = result[0], result[1]
    return score, text


@paddle.no_grad()
def infer():
    # 提取音频特征
    s = time.time()
    feature = audio_process.process_utterance(args.audio_path)
    feature = paddle.to_tensor([feature], dtype=paddle.float32)
    audio_len = paddle.to_tensor(feature.shape[2], dtype=paddle.int64)
    print('加载音频和预处理时间：%dms' % round((time.time() - s) * 1000))
    # 执行识别
    s = time.time()
    out = model(feature, audio_len)[0]
    print('执行预测时间：%dms' % round((time.time() - s) * 1000))
    # 执行解码
    s = time.time()
    score, text = decoder(out.numpy(), vocab_list)
    print('解码消耗时间：%dms' % round((time.time() - s) * 1000))
    return score, text


if __name__ == '__main__':
    start = time.time()
    result_score, result_text = infer()
    print('识别总时间：%dms，识别结果：%s，得分：%f' % (round((time.time() - start) * 1000), result_text, result_score))
