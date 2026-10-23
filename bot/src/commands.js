// 斜線指令的定義（機器人上線時自動註冊到伺服器）
import { SlashCommandBuilder } from 'discord.js';

export const commands = [
  new SlashCommandBuilder().setName('開始').setDescription('機器人進入你所在的語音頻道，開始收音與計時'),
  new SlashCommandBuilder().setName('結束').setDescription('離開語音頻道，停止計時'),
  new SlashCommandBuilder().setName('狀態').setDescription('目前是否在收音、累計多久'),
  new SlashCommandBuilder()
    .setName('排行榜')
    .setDescription('媽媽系列排行榜')
    .addSubcommand((s) => s.setName('成員').setDescription('誰講最多'))
    .addSubcommand((s) => s.setName('髒話').setDescription('哪句最常出現')),
  new SlashCommandBuilder()
    .setName('查詢')
    .setDescription('查看某人的紀錄')
    .addUserOption((o) => o.setName('成員').setDescription('要查的人').setRequired(true)),
  new SlashCommandBuilder()
    .setName('詞庫')
    .setDescription('管理要統計的句子')
    .addSubcommand((s) =>
      s
        .setName('新增')
        .setDescription('新增一句（已存在的話會合併變體）')
        .addStringOption((o) => o.setName('句子').setDescription('例如：你媽死了').setRequired(true))
        .addStringOption((o) => o.setName('變體').setDescription('其他寫法，用逗號分隔，例如：你馬死了, 尼瑪死了')),
    )
    .addSubcommand((s) =>
      s
        .setName('刪除')
        .setDescription('從詞庫刪除一句（過去紀錄會保留）')
        .addStringOption((o) => o.setName('句子').setDescription('要刪除的句子').setRequired(true)),
    )
    .addSubcommand((s) => s.setName('列表').setDescription('列出目前的詞庫'))
    .addSubcommand((s) => s.setName('重新載入').setDescription('重新讀取手動編輯過的詞庫與同義規則檔案')),
  new SlashCommandBuilder()
    .setName('同義')
    .setDescription('管理同義規則（語助詞、錯字等）')
    .addSubcommand((s) =>
      s
        .setName('新增')
        .setDescription('例如：啦 → 了，讓「你媽死啦」算成「你媽死了」')
        .addStringOption((o) => o.setName('變體').setDescription('例如：啦').setRequired(true))
        .addStringOption((o) => o.setName('標準').setDescription('例如：了（留空代表直接刪掉這個字）')),
    )
    .addSubcommand((s) =>
      s
        .setName('刪除')
        .setDescription('刪除一條同義規則')
        .addStringOption((o) => o.setName('變體').setDescription('要刪除的變體').setRequired(true)),
    )
    .addSubcommand((s) => s.setName('列表').setDescription('列出目前的同義規則')),
].map((c) => c.toJSON());

// 只有 OWNER_ID 能用的指令
export const ownerOnly = new Set(['開始', '結束', '詞庫', '同義']);
