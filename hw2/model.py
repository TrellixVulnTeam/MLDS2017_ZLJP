import tensorflow as tf
import numpy as np

class Video_Caption_Generator():
	def __init__(self, args, n_vocab, infer):
		# model parameters
		self.dim_image 		= args.dim_image
		self.n_video_step 	= args.n_video_step
		self.n_caption_step = args.n_caption_step
		self.dim_hidden 	= args.dim_hidden
		self.n_lstm_step 	= args.n_lstm_step
		self.batch_size 	= args.batch_size
		self.learning_rate	= args.learning_rate
		self.grad_clip		= args.grad_clip
		self.n_vocab 		= n_vocab

		# model components
		# two LSTM layers
		# word embedding for input
		with tf.device("/cpu:0"):
			self.Wemb = tf.Variable(tf.random_uniform([self.n_vocab, self.dim_hidden],-0.1,0.1), name="Wemb")
	
		self.lstm1 = tf.contrib.rnn.BasicLSTMCell(self.dim_hidden, state_is_tuple=False)
		self.lstm2 = tf.contrib.rnn.BasicLSTMCell(self.dim_hidden, state_is_tuple=False)

		# image embedding
		self.embed_image_W = tf.Variable(tf.random_uniform([self.dim_image, self.dim_hidden],-0.1,0.1), name="embed_image_W")
		self.embed_image_b = tf.Variable(tf.zeros([self.dim_hidden]), name="embed_image_b")

		# word embedding for output
		self.embed_word_W  = tf.Variable(tf.random_uniform([self.dim_hidden,self.n_vocab],-0.1,0.1), name="embed_word_W")
		self.embed_word_b  = tf.Variable(tf.zeros([self.n_vocab]), name="embed_word_b")

		if infer == False:
			# input
			self.video = tf.placeholder(tf.float32, [self.batch_size, self.n_video_step, self.dim_image])
			self.video_mask = tf.placeholder(tf.float32, [self.batch_size, self.n_video_step])

			# output
			self.caption = tf.placeholder(tf.int32, [self.batch_size, self.n_caption_step+1]) # int32 for embedding_look_up
			self.caption_mask = tf.placeholder(tf.float32, [self.batch_size, self.n_caption_step+1])

			# results
			pred_probs = []
			loss = 0.0

			### Step1: transform video into embedded video ###
			video_flat = tf.reshape(self.video, [-1, self.dim_image]) # (batch_size*n_video_step, dim_image)
			image_embed = tf.nn.xw_plus_b(video_flat, self.embed_image_W, self.embed_image_b)
			image_embed = tf.reshape(image_embed, [self.batch_size, self.n_video_step, self.dim_hidden])

			### Step2: (encoding stage) embedded images into LSTM ###
			# initialization states in 2 LSTM layers
			state1 = tf.zeros([self.batch_size, self.lstm1.state_size])
			state2 = tf.zeros([self.batch_size, self.lstm2.state_size])

			# padding when entering LSTM2
			# A word is embedded as a vector of dim_hidden by Wemb, so the padding vector is with dim_hidden
			padding = tf.zeros([self.batch_size, self.dim_hidden]) 

			for i in range(0,self.n_video_step):
				if i == 0:
					with tf.variable_scope("LSTM1"):
						output1, state1 = self.lstm1(image_embed[:,i,:],state1)
					with tf.variable_scope("LSTM2"):
						output2, state2 = self.lstm2(tf.concat([padding, output1],1), state2)
				else:
					with tf.variable_scope("LSTM1",reuse=True):
						output1, state1 = self.lstm1(image_embed[:,i,:],state1)
					with tf.variable_scope("LSTM2",reuse=True):
						output2, state2 = self.lstm2(tf.concat([padding, output1],1), state2)

			### Step 3: (decoding stage) acquire prediction from LSTM2 output ###

			for i in range(0, self.n_caption_step):
				with tf.device("/cpu:0"):
					current_word_embed = tf.nn.embedding_lookup(self.Wemb, self.caption[:,i])

				with tf.variable_scope("LSTM1",reuse=True):
					output1, state1 = self.lstm1(padding, state1)
				with tf.variable_scope("LSTM2",reuse=True):
					output2, state2 = self.lstm2(tf.concat([current_word_embed,output1],1),state2)

				### Step 4: calculate loss ### 
				# create answer 
				answer_index_in_vocab = self.caption[:,i+1]
				answer_index_in_vocab = tf.expand_dims(answer_index_in_vocab, 1)
				batch_index	= tf.expand_dims(tf.range(0, self.batch_size, 1), 1)
				sparse_mat 	= tf.concat([batch_index, answer_index_in_vocab], 1)
				answer_in_onehot = tf.sparse_to_dense(sparse_mat, np.asarray([self.batch_size, self.n_vocab]), 1.0, 0.0)

				# acquire output
				logits = tf.nn.xw_plus_b(output2, self.embed_word_W, self.embed_word_b)
				cross_entropy = tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=answer_in_onehot)
				cross_entropy = cross_entropy * self.caption_mask[:,i]

				pred_probs.append(logits)

				this_loss = tf.reduce_sum(cross_entropy)/self.batch_size
				loss = loss + this_loss

			self.tf_loss = loss
			self.tf_probs = pred_probs

			tvars = tf.trainable_variables()
			grads, _ = tf.clip_by_global_norm(tf.gradients(self.tf_loss, tvars), clip_norm = self.grad_clip)
			optimizer = tf.train.AdamOptimizer(self.learning_rate)
			self.train_op = optimizer.apply_gradients(zip(grads, tvars))
			# self.train_op = tf.train.AdamOptimizer(self.learning_rate).minimize(self.tf_loss)

		else: # infer == True
			self.video = tf.placeholder(tf.float32, [1, self.n_video_lstm_step, self.dim_image])
			self.video_mask = tf.placeholder(tf.float32, [1, self.n_video_lstm_step])

			video_flat = tf.reshape(video, [-1, self.dim_image])
			image_emb = tf.nn.xw_plus_b(video_flat, self.encode_image_W, self.encode_image_b)
			image_emb = tf.reshape(image_emb, [1, self.n_video_lstm_step, self.dim_hidden])

			state1 = tf.zeros([1, self.lstm1.state_size])
			state2 = tf.zeros([1, self.lstm2.state_size])
			padding = tf.zeros([1, self.dim_hidden])

			gen_caption_idx = []

			pred_probs = []
			embeds = []

			for i in range(0,self.n_video_step):
				if i == 0:
					with tf.variable_scope("LSTM1"):
						output1, state1 = self.lstm1(image_embed[:,i,:],state1)
					with tf.variable_scope("LSTM2"):
						output2, state2 = self.lstm2(tf.concat([padding, output1],1), state2)
				else:
					with tf.variable_scope("LSTM1",reuse=True):
						output1, state1 = self.lstm1(image_embed[:,i,:],state1)
					with tf.variable_scope("LSTM2",reuse=True):
						output2, state2 = self.lstm2(tf.concat([padding, output1],1), state2)

			for i in range(0, self.n_caption_step):

				if i == 0:
					# For testing, here the first word of caption must be <BOS>, 
					# <BOS> is defined at the index of 0 in function build_word_vocabuary in utils.py.	
					with tf.device("/cpu:0"):
						current_word_embed = tf.nn.embedding_lookup(self.Wemb, tf.zeros([0],dtype=tf.int32))

				with tf.variable_scope("LSTM1",reuse=True):
					output1, state1 = self.lstm1(padding, state1)
				with tf.variable_scope("LSTM2",reuse=True):
					output2, state2 = self.lstm2(tf.concat([current_word_embed,output1],1),state2)

				logits = tf.nn.xw_plus_b( output2, self.embed_word_W, self.embed_word_b)
				max_prob_index = tf.argmax(logits, 1)[0]
				gen_caption_idx.append(max_prob_index)
				pred_probs.append(logits)

				# update current_word_embed
				with tf.device("/cpu:0"):
					current_word_embed = tf.nn.embedding_lookup(self.Wemb, max_prob_index)
					# current_word_embed = tf.expand_dims(current_word_embed, 0)
				embeds.append(current_embed)

			self.gen_caption_idx = gen_caption_idx
			self.pred_probs = pred_probs
