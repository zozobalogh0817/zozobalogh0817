---
layout: page
title: Projects
options: { toc: false, menuItem: true, archived: false }
---

<img src="https://user-images.githubusercontent.com/67690333/148852202-984c4d7d-498d-43f4-88eb-49b2a7b4b026.gif" id="egggif" style="display: none">

> Type ***cabata***

<script>
var egg = new Egg();
egg
  .addCode("c,a,b,a,t,a", function() {
    jQuery('#egggif').fadeIn(500, function() {
      window.setTimeout(function() { jQuery('#egggif').hide(); }, 5000);
    });
  })
  .addHook(function(){
    console.log("Hook called for: " + this.activeEgg.keys);
    console.log(this.activeEgg.metadata);
  }).listen();
</script>

![image](https://user-images.githubusercontent.com/67690333/148851416-6d526fd0-9f04-42ae-a542-dff77eefcd72.png)
