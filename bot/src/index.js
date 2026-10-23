import { Client, EmbedBuilder, Events, GatewayIntentBits, MessageFlags } from 'discord.js';
import { VoiceConnectionStatus, entersState, joinVoiceChannel } from '@discordjs/voice';
import { ApiError, call, sendAudio } from './api.js';
import { commands, ownerOnly } from './commands.js';
import { config } from './config.js';
import { Recorder } from './recorder.js';

const HEARTBEAT_MS = 60_000;

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });

/** 目前的收音狀態：{ connection, recorder, heartbeat } */
let session = null;

function embed({ title, description }) {
  return new EmbedBuilder().setTitle(title).setDescription(description || '​').setColor(0xe0565b);
}

async function displayName(guild, userId) {
  const member = guild.voiceStates.cache.get(userId)?.member ?? (await guild.members.fetch(userId).catch(() => null));
  return member?.displayName ?? userId;
}

async function startSession(interaction) {
  const channel = interaction.member.voice?.channel;
  if (!channel) {
    return interaction.reply({ content: '請先進入一個語音頻道', flags: MessageFlags.Ephemeral });
  }
  if (session) {
    return interaction.reply({ content: '已經在統計中了', flags: MessageFlags.Ephemeral });
  }
  await interaction.deferReply();

  const connection = joinVoiceChannel({
    channelId: channel.id,
    guildId: channel.guild.id,
    adapterCreator: channel.guild.voiceAdapterCreator,
    selfDeaf: false,
    selfMute: true,
  });
  try {
    await entersState(connection, VoiceConnectionStatus.Ready, 20_000);
    await call('POST', '/session/start');
  } catch (err) {
    connection.destroy();
    const reason = err instanceof ApiError ? err.message : '連不上語音頻道';
    return interaction.editReply(`無法開始：${reason}`);
  }

  const guild = channel.guild;
  const recorder = new Recorder(connection, async (userId, pcm) => {
    try {
      await sendAudio(userId, await displayName(guild, userId), pcm);
    } catch (err) {
      console.warn(`音訊送不出去：${err.message}`);
    }
  });
  recorder.start();
  const heartbeat = setInterval(() => call('POST', '/heartbeat').catch(() => {}), HEARTBEAT_MS);
  session = { connection, recorder, heartbeat };

  // 斷線時先試著重連，5 秒內接不回來就結束這次統計
  connection.on(VoiceConnectionStatus.Disconnected, async () => {
    try {
      await Promise.race([
        entersState(connection, VoiceConnectionStatus.Signalling, 5_000),
        entersState(connection, VoiceConnectionStatus.Connecting, 5_000),
      ]);
    } catch {
      const result = await stopSession().catch(() => null);
      if (result) interaction.followUp({ content: '語音連線中斷，已自動結束統計', embeds: [embed(result)] });
    }
  });

  await interaction.editReply({
    embeds: [embed({ title: '開始統計', description: `機器人正在 <#${channel.id}> 收音，說話會被統計喔` })],
  });
}

async function stopSession() {
  if (session) {
    const { connection, recorder, heartbeat } = session;
    session = null;
    clearInterval(heartbeat);
    recorder.stop();
    if (connection.state.status !== VoiceConnectionStatus.Destroyed) connection.destroy();
  }
  return call('POST', '/session/stop');
}

async function handle(interaction) {
  const name = interaction.commandName;
  if (ownerOnly.has(name) && interaction.user.id !== config.ownerId) {
    return interaction.reply({ content: '只有機器人管理者可以用這個指令', flags: MessageFlags.Ephemeral });
  }
  const options = interaction.options;
  const sub = options.getSubcommand(false);
  const reply = async (method, path, body) => interaction.reply({ embeds: [embed(await call(method, path, body))] });

  switch (name) {
    case '開始':
      return startSession(interaction);
    case '結束':
      return interaction.reply({ embeds: [embed(await stopSession())] });
    case '狀態':
      return reply('GET', '/status');
    case '排行榜':
      return reply('GET', sub === '成員' ? '/leaderboard/members' : '/leaderboard/phrases');
    case '查詢':
      return reply('GET', `/users/${options.getUser('成員', true).id}`);
    case '詞庫': {
      const phrase = options.getString('句子');
      const variants = (options.getString('變體') ?? '').split(/[,，、]/).map((v) => v.trim()).filter(Boolean);
      if (sub === '新增') return reply('POST', '/words', { phrase, variants });
      if (sub === '刪除') return reply('POST', '/words/remove', { phrase });
      if (sub === '列表') return reply('GET', '/words');
      return reply('POST', '/words/reload');
    }
    case '同義': {
      const variant = options.getString('變體');
      if (sub === '新增') return reply('POST', '/synonyms', { variant, standard: options.getString('標準') ?? '' });
      if (sub === '刪除') return reply('POST', '/synonyms/remove', { variant });
      return reply('GET', '/synonyms');
    }
  }
}

client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isChatInputCommand()) return;
  try {
    await handle(interaction);
  } catch (err) {
    const content = err instanceof ApiError ? err.message : '發生錯誤，詳情請看機器人的視窗';
    if (!(err instanceof ApiError)) console.error(err);
    const send = interaction.deferred || interaction.replied ? interaction.followUp : interaction.reply;
    await send.call(interaction, { content, flags: MessageFlags.Ephemeral }).catch(() => {});
  }
});

client.once(Events.ClientReady, async (c) => {
  // 上次若沒按 /結束 就關掉，先把那次以最後收到聲音的時間結束
  await call('POST', '/session/recover').catch(() => console.warn('Python 服務還沒啟動，請記得開啟它'));
  const guild = await c.guilds.fetch(config.guildId);
  await guild.commands.set(commands);
  console.log(`已登入為 ${c.user.tag}，指令已註冊到「${guild.name}」`);
});

async function shutdown() {
  if (session) await stopSession().catch(() => {});
  await client.destroy();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

client.login(config.token);
