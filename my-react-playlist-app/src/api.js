// src/api.js

/**
 * A helper function to get the authentication headers from local storage.
 */
const getAuthHeaders = () => {
  const accessToken = localStorage.getItem('spotify_access_token');
  if (!accessToken) {
    throw new Error("User not logged in");
  }
  return {
    'Authorization': `Bearer ${accessToken}`,
    'X-Refresh-Token': localStorage.getItem('spotify_refresh_token') || '',
    'X-Expires-At': localStorage.getItem('spotify_expires_at') || '0',
    'Content-Type': 'application/json'
  };
};

/**
 * Sends a chat message to the backend.
 * (จับคู่กับ sendMessageToChatbot ใน AppContext)
 */
export const sendMessageToChatbot = async (message, intent = null) => {
  let headers = { 'Content-Type': 'application/json' };
  try {
    headers = { ...headers, ...getAuthHeaders() };
  } catch (error) {
    console.log("Sending chat message as a guest.");
  }

  const response = await fetch('/chat', {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({ message, intent })
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Server error');
  }
  return response.json();
};
// Alias ไว้เผื่อที่อื่นเรียกใช้ชื่อเดิม
export const postChatMessage = sendMessageToChatbot;

/**
 * Fetches the current user's Spotify profile.
 */
export const fetchUserProfile = async () => {
    const headers = getAuthHeaders();
    const response = await fetch('/me', { headers });
    if (!response.ok) {
        throw new Error('Failed to fetch user profile');
    }
    return response.json();
};

/**
 * Fetches pinned playlists.
 * (จับคู่กับ getPinnedPlaylistsAPI ใน AppContext)
 */
export const getPinnedPlaylistsAPI = async () => {
  const headers = getAuthHeaders();
  const response = await fetch('/pinned_playlists', { headers });
  if (!response.ok) {
    throw new Error('Could not fetch pinned playlists');
  }
  return response.json();
};
// Alias
export const fetchPinnedPlaylists = getPinnedPlaylistsAPI;

/**
 * Pins a new playlist.
 * (จับคู่กับ pinPlaylistAPI ใน AppContext)
 */
export const pinPlaylistAPI = async (playlistName, songs, recommendationText) => {
    const simplifiedSongs = songs.map(song => ({
        uri: song.uri, name: song.name, artists: song.artists.map(a => ({ name: a.name })),
        album: { images: song.album.images }, external_urls: { spotify: song.external_urls.spotify }
    }));

    const response = await fetch('/pin_playlist', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ 
            playlist_name: playlistName, 
            songs: simplifiedSongs, 
            recommendation_text: recommendationText 
        })
    });
    if (!response.ok) {
        throw new Error('Failed to pin playlist');
    }
};
// Alias
export const pinPlaylist = pinPlaylistAPI;

/**
 * Sends feedback (like/dislike).
 * (จับคู่กับ sendFeedbackAPI ใน AppContext)
 */
export const sendFeedbackAPI = async (trackUri, feedback) => {
    await fetch('/feedback', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ track_uri: trackUri, feedback: feedback })
    });
};
// Alias
export const sendFeedback = sendFeedbackAPI;

/**
 * Fetches song details.
 * (จับคู่กับ getSongDetailsAPI ใน AppContext)
 */
export const getSongDetailsAPI = async (songUri) => {
    const response = await fetch(`/song_details/${encodeURIComponent(songUri)}`, { 
        headers: getAuthHeaders() 
    });
    if (!response.ok) {
        throw new Error('Failed to fetch song details');
    }
    return response.json();
};
// Alias
export const fetchSongDetails = getSongDetailsAPI;

/**
 * Creates a Spotify playlist.
 * (จับคู่กับ createPlaylistAPI ใน AppContext)
 */
export const createPlaylistAPI = async (playlistName, trackUris) => {
    const response = await fetch('/create_playlist', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ playlist_name: playlistName, track_uris: trackUris })
    });
    if (!response.ok) {
        throw new Error('Failed to create playlist');
    }
    return response.json();
};
// Alias
export const createSpotifyPlaylist = createPlaylistAPI;

/**
 * Deletes a pinned playlist.
 * (จับคู่กับ deletePinnedPlaylistAPI ใน AppContext)
 */
export const deletePinnedPlaylistAPI = async (pinId) => {
  const response = await fetch(`/pinned_playlists/${pinId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error('Failed to delete pinned playlist');
  }
  return { success: true };
};
// Alias
export const deletePinnedPlaylist = deletePinnedPlaylistAPI;

/**
 * Updates a pinned playlist.
 * (จับคู่กับ updatePinnedPlaylistAPI ใน AppContext)
 */
export const updatePinnedPlaylistAPI = async (pinId, newName, songs) => {
  const response = await fetch(`/pinned_playlists/${pinId}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      playlist_name: newName,
      songs: songs 
    })
  });
  if (!response.ok) {
    throw new Error('Failed to update playlist');
  }
  return { success: true };
};
// Alias
export const updatePinnedPlaylist = updatePinnedPlaylistAPI;

/**
 * Summarizes a playlist.
 * (จับคู่กับ summarizePlaylistAPI ใน AppContext)
 */
export const summarizePlaylistAPI = async (songUris) => {
  const response = await fetch('/summarize_playlist', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ song_uris: songUris })
  });
  if (!response.ok) {
    throw new Error('Failed to summarize playlist');
  }
  return response.json(); 
};
// Alias
export const summarizePlaylist = summarizePlaylistAPI;

/**
 * Fetches dynamic suggested prompts.
 * (จับคู่กับ getSuggestedPromptsAPI ใน AppContext)
 */
export const getSuggestedPromptsAPI = async () => {
  try {
    const headers = getAuthHeaders();
    const response = await fetch('/suggested_prompts', { headers });
    if (!response.ok) {
      throw new Error('Could not fetch suggestions');
    }
    return response.json();
  } catch (error) {
    console.warn("Could not fetch dynamic prompts, using default.", error.message);
    return { prompts: [ '🎵 แนะนำเพลงส่วนตัวให้หน่อย', '📈 ขอเพลงฮิตติดชาร์ต', '🎧 หาเพลงเศร้าๆ' ] };
  }
};
// Alias
export const fetchSuggestedPrompts = getSuggestedPromptsAPI;